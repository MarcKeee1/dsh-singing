import {homedir} from 'node:os';
import {join,resolve,isAbsolute,dirname} from 'node:path';
import {readFile} from 'node:fs/promises';
export function locations(options={}){
  const home=process.env.DSH_HOME||join(homedir(),'.dsh');
  const data=resolve(options.dataDir||(options.configFile?dirname(options.configFile):join(home,'singing')));
  return {dataDir:data,configFile:resolve(options.configFile||join(data,'backend.json')),python:options.pythonPath||join(data,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python'),delivery:options.delivery||'auto',timeoutMs:options.timeoutMs??0};
}
export async function backendOutput(configFile){
  let config;try{config=JSON.parse(await readFile(configFile,'utf8'))}catch{throw Error('唱歌后端未配置，请先运行安装脚本并设置参考音频')}
  const base=dirname(configFile),data=resolve(base,config.dataDir||'.');
  return isAbsolute(config.outputDir||'')?resolve(config.outputDir):resolve(base,config.outputDir||join(data,'output'));
}
