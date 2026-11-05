import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {win32} from 'node:path';
import {homedir} from 'node:os';
import {voiceTarget} from './say-voice.js';
import {withLocalGpu} from './local-gpu-queue.js';

const ROOT=(process.env.DSH_SINGING_ROOT || win32.join(homedir(),'.dsh','singing')).replaceAll('\\','/');
const MEDIA=win32.join(process.env.DSH_HOME || win32.join(homedir(),'.dsh'),'media','onebot','voice').replaceAll('\\','/');
const PYTHON=process.env.DSH_SINGING_PYTHON || ROOT+'/.venv/Scripts/python.exe';

export function runSinging(request,signal,spawnProcess=spawn,{cacheOnly=false}={}){
  return new Promise((resolve,reject)=>{
    signal?.throwIfAborted();
    const child=spawnProcess(PYTHON,[ROOT+'/cover.py','--request',request,...(cacheOnly?['--cache-only']:[])],{cwd:ROOT,windowsHide:true,shell:false,stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8'}});
    let stdout='',stderr='',stopReason,settled=false;
    const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);error?reject(error):resolve(value);};
    const stop=error=>{if(stopReason||settled)return;stopReason=error;if(process.platform==='win32'&&child.pid){const killer=spawn('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,shell:false,stdio:'ignore'});killer.once('error',()=>child.kill());}else child.kill();};
    const abort=()=>stop(new Error('唱歌已取消，未发送'));
    const timer=setTimeout(()=>stop(new Error('唱歌处理超时，未发送')),25*60_000);
    signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();
    child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8');
    child.stdout.on('data',chunk=>stdout=(stdout+chunk).slice(-32768));
    child.stderr.on('data',chunk=>stderr=(stderr+chunk).slice(-2048));
    child.once('error',error=>finish(error));
    child.once('close',code=>{
      if(stopReason)return finish(stopReason);
      try{const result=JSON.parse(stdout.trim());if(code!==0||!result.ok)throw Error(result.error||'唱歌生成失败');finish(null,result);}
      catch(error){finish(new Error(error.message+(stdout.trim()?'':'; '+stderr.trim())));}
    });
  });
}

export function singingAction(bridge,limits,readMedia,run=runSinging){
  return async(args,exec)=>{
    let sending=false;
    const check=()=>{exec.signal?.throwIfAborted();const target=voiceTarget(exec.agent,bridge);if(!target||bridge.chatForSession(String(exec.agent.session.id))!==target.chat||!bridge.connected)throw Error('当前 QQ 会话不可发送，未唱歌');return target.chat;};
    try{
      const chat=check(),title=String(args.song??'').trim(),artist=String(args.artist??'').trim();
      if(!title||title.length>160)throw Error('请提供歌名，最多 160 字');
      if(!artist||artist.length>80)throw Error('请保留原唱歌手；不能在查找失败后删除歌手改用同名翻唱');
      const gate=await bridge.mediaSendRoots(exec.agent.session.id);
      let source,seconds=args.duration_seconds??null;
      if(args.source_path){
        if(!gate.isTurnAdmin)throw Error('原曲文件需管理员导入；普通群友可以点已导入曲目');
        if(!/\.(mp3|wav|flac|m4a|ogg|opus|aac)$/i.test(args.source_path))throw Error('需要本地音频文件');
        const bytes=await readMedia(args.source_path,100*1024*1024,gate.roots);
        if(!bytes.startsWith('base64://'))throw Error('原曲读取失败');
        const imported=ROOT+'/imports/'+randomUUID()+win32.extname(args.source_path).toLowerCase();
        await mkdir(ROOT+'/imports',{recursive:true});await writeFile(imported,Buffer.from(bytes.slice(9),'base64'),{flag:'wx'});
        source=imported;
      }
      const start=args.start_seconds===undefined||args.start_seconds===null?null:Number(args.start_seconds),hint=String(args.chorus_hint??'').trim(),occurrence=Number(args.lyric_occurrence??1);seconds=seconds===null?null:Number(seconds);
      if((start!==null&&(!Number.isFinite(start)||start<0||start>7200))||(seconds!==null&&(!Number.isFinite(seconds)||seconds<5||seconds>90)))throw Error('默认唱完一段副歌，指定时长需在 5–90 秒之间');
      if(hint&&start!==null)throw Error('歌词起句和秒数起点请选一种');
      if(hint&&(hint.replace(/[\s\p{P}\p{S}]/gu,'').length<4||hint.length>120))throw Error('请给至少四个字的起唱歌词，最多120字');
      if(!Number.isInteger(occurrence)||occurrence<1||occurrence>10||(!hint&&occurrence!==1))throw Error('歌词出现次数需为1到10的整数，并提供对应歌词');
      const job=randomUUID(),output=MEDIA+'/sing-'+job+'.mp3',request=ROOT+'/requests/'+job+'.json';
      await mkdir(ROOT+'/requests',{recursive:true});await mkdir(MEDIA,{recursive:true});
      await writeFile(request,JSON.stringify({title,artist,chorus_hint:hint,lyric_occurrence:occurrence,positionVersion:1,source_url:String(args.source_url??'').slice(0,500),source,output,start,duration:seconds}),{flag:'wx'});
      // A finished recording needs neither a music lookup nor a GPU slot.
      // A miss joins the shared queue; the backend checks again once admitted.
      let result=await run(request,exec.signal,undefined,{cacheOnly:true});
      if(result.cacheMiss===true)result=await withLocalGpu(()=>{
        if(check()!==chat)throw Error('会话已变化，未发送');
        return run(request,exec.signal);
      },exec.signal);
      if(check()!==chat)throw Error('会话已变化，未发送');
      if(!result.quality?.passed||!Number.isFinite(result.seconds)||result.seconds>90||win32.normalize(result.path)!==win32.normalize(output))throw Error('生成结果、时长或音准校验无效，未发送');
      const currentGate=await bridge.mediaSendRoots(exec.agent.session.id);
      const file=await readMedia(result.path,limits.maxVoiceBytes,currentGate.roots);
      if(check()!==chat)throw Error('会话已变化，未发送');
      sending=true;
      const message_id=await bridge.sendSegments(chat,[{type:'record',data:{file}}]);
      return {ok:true,message_id:message_id??null,song:title,artist:result.sourceInfo?.artist,seconds:result.seconds,cacheHit:result.cacheHit,pitchChecked:true,source:result.sourceInfo?.sourcePage,startSeconds:result.sourceInfo?.sourceStartSeconds,startMode:result.sourceInfo?.positionRequest?.mode,lyricOccurrence:result.sourceInfo?.positionRequest?.occurrence,segment:result.sourceInfo?.chorusMethod?.includes('complete_section')?'完整副歌':'歌声片段',note:'翻唱已发送一次；不要重复发送音频或歌词。'};
    }catch(error){return {ok:false,error:String(error.message??error),delivery:sending?'unknown':'not_sent',note:sending?'送达结果未确认，不自动重发。':'没有把歌词改成朗读，也没有发送未通过音准检查的音频。'};}
  };
}
