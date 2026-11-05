import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const script=fileURLToPath(new URL('../python/cover.py',import.meta.url));
export function runBackend(request,config,signal,{cacheOnly=false,spawnProcess=spawn}={}){
  return new Promise((resolve,reject)=>{
    signal?.throwIfAborted();
    const child=spawnProcess(config.python,[script,'--request',request,...cacheOnly?['--cache-only']:[]],{windowsHide:true,shell:false,detached:process.platform!=='win32',stdio:['ignore','pipe','pipe'],env:{...process.env,DSH_SINGING_CONFIG:config.configFile,PYTHONIOENCODING:'utf-8'}});
    let stdout='',stderr='',stopping,done=false;
    const finish=(error,value)=>{if(done)return;done=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);error?reject(error):resolve(value)};
    const stop=error=>{if(done||stopping)return;stopping=error;if(process.platform==='win32'&&child.pid){const killer=spawn('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,shell:false,stdio:'ignore'});killer.once('error',()=>child.kill())}else{try{process.kill(-child.pid,'SIGTERM')}catch{child.kill('SIGTERM')}}};
    const abort=()=>stop(Error('唱歌已取消，未发送'));
    const timer=config.timeoutMs>0?setTimeout(()=>stop(Error('唱歌处理超时，未发送')),config.timeoutMs):null;
    signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();
    child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8');
    child.stdout.on('data',s=>stdout=(stdout+s).slice(-65536));child.stderr.on('data',s=>stderr=(stderr+s).slice(-4096));
    child.once('error',()=>finish(Error('无法启动唱歌后端，请核对 Python 路径并运行 doctor.py')));
    child.once('close',code=>{if(stopping)return finish(stopping);try{const value=JSON.parse(stdout.trim());if(code!==0||value.ok!==true){const error=Error(value.error||'本地歌声处理失败');error.result=value;throw error}finish(null,value)}catch(error){finish(error.result?error:Error(stdout.trim()?error.message:'本地歌声处理失败，请检查后端任务日志'))}});
  });
}
