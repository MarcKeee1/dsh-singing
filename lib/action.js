import {randomUUID} from 'node:crypto';
import {mkdir,writeFile,stat,realpath} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {backendOutput} from './config.js';
import {runBackend} from './runner.js';
import {withLocalGpu} from './queue.js';

export function validate(args){
  const title=String(args.song||'').trim(),artist=String(args.artist||'').trim();
  if(!title||title.length>160||!artist||artist.length>80)throw Error('请提供准确歌名和指定歌手/版本');
  const duration=args.duration_seconds??null,start=args.start_seconds??null,hint=String(args.chorus_hint||'').trim(),occurrence=args.lyric_occurrence??1;
  if(duration!==null&&(!Number.isFinite(duration)||duration<5))throw Error('时长至少5秒');
  if(start!==null&&(!Number.isFinite(start)||start<0))throw Error('起点秒数无效');
  if(hint&&(start!==null||hint.replace(/[\s\p{P}\p{S}]/gu,'').length<4||hint.length>120))throw Error('歌词起句至少四个字，且不能同时指定秒数');
  if(!Number.isInteger(occurrence)||occurrence<1||occurrence>10||(!hint&&occurrence!==1))throw Error('歌词次数需为1到10，并提供起句');
  if(args.source_path&&args.source_url)throw Error('本地音频和视频链接请选择一种');
  const url=String(args.source_url||'');if(url.length>500)throw Error('视频链接过长');
  const mode=args.mode||((start!==null||hint)?'from':'excerpt');
  if(!['full','chorus','from','excerpt'].includes(mode))throw Error('无效唱歌模式');
  if(mode==='full'&&(duration!==null||start!==null||hint))throw Error('整首模式不能同时指定片段时长或起点');
  if(mode==='chorus'&&(start!==null||hint))throw Error('副歌与指定起点请选择一种');
  if(mode==='from'&&start===null&&!hint)throw Error('请指定起唱秒数或歌词');
  return {title,artist,mode,duration,start,chorus_hint:hint,lyric_occurrence:occurrence,positionVersion:1,source_url:url,...args.source_path?{source:String(args.source_path)}:{}};
}

export function createAction(ctx,config,turns,{run=runBackend,queue=withLocalGpu}={}){
  return async(args,exec)=>{
    let state,key,sending=false;
    try{
      exec.signal?.throwIfAborted();const request=validate(args),agent=exec.agent;
      if(!agent?.session?.id)throw Error('需要当前 DSH 会话');
      const session=String(agent.session.id),toolService=agent.ctx?.tools||ctx.tools;
      const isQQ=/^onebot-(?:private|group)-/.test(session),shouldSend=config.delivery==='qq'||(config.delivery==='auto'&&isQQ);
      if(shouldSend&&(!isQQ||!toolService.get('qq_send_voice',agent)))throw Error('当前会话未启用 qq_send_voice；请配置 OneBot 语音工具，或将 delivery 设为 file');
      state=turns.get(session)?.deliveries;
      key=JSON.stringify(request);
      if(state?.has(key))return {...state.get(key),duplicateSuppressed:true};
      const outputDir=await backendOutput(config.configFile),job=randomUUID(),output=join(outputDir,'sing-'+job+'.mp3');
      const requestDir=join(config.dataDir,'requests');await mkdir(requestDir,{recursive:true});
      const requestFile=join(requestDir,job+'.json');await writeFile(requestFile,JSON.stringify({...request,output}),{flag:'wx'});
      let result=await run(requestFile,config,exec.signal,{cacheOnly:true});
      if(result.cacheMiss===true)result=await queue(()=>run(requestFile,config,exec.signal),exec.signal);
      exec.signal?.throwIfAborted();
      if(resolve(result.path||'')!==resolve(output)||!result.quality?.passed||!Number.isFinite(result.seconds)||result.seconds<5)throw Error('歌声结果未通过路径、音准或时长检查，未发送');
      if(await realpath(output)!==resolve(output))throw Error('输出路径异常，未发送');
      if((await stat(output)).size<1)throw Error('音频文件为空，未发送');
      const value={ok:true,song:request.title,artist:request.artist,mode:request.mode,seconds:result.seconds,cacheHit:result.cacheHit===true,cacheMode:result.cacheMode,source:result.sourceInfo?.sourcePage??null,delivery:'file',path:output};
      if(shouldSend){
        if(String(agent.session.id)!==session)throw Error('当前会话已变化，未发送');
        if(!toolService.get('qq_send_voice',agent))throw Error('语音工具已停用，未发送');
        state?.set(key,{ok:false,delivery:'unknown',error:'已尝试发送，结果未确认；不要自动重发'});sending=true;
        // Dispatch through the real registry: existing policies, guards and
        // current-chat routing stay in force. Never call a raw OneBot API.
        const sent=await toolService.execute({name:'qq_send_voice',arguments:{path:output},agent,signal:exec.signal,parent:exec.token,callId:randomUUID(),rootCallId:exec.rootCallId||exec.callId});
        if(sent.isError||sent.value?.sent!==true)throw Error('发送未确认，请核对聊天记录；不要自动重发');
        value.delivery='sent';value.messageId=sent.value.messageId??null;delete value.path;
      }
      value.note=shouldSend?'歌声已发送一次，不要重复发送，也不要说没有唱成。':'已生成本地 MP3，可打开 path 播放；没有发送到其他会话。';
      state?.set(key,value);return value;
    }catch(error){const value={ok:false,delivery:sending?'unknown':'not_sent',error:String(error.message||error).slice(0,600),note:sending?'不要自动重发。':'按实际错误说明，不要擅自换歌手，不要把歌词朗读当唱歌。'};if(sending)state?.set(key,value);return value}
  };
}
