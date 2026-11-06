import {homedir} from 'node:os';
import {join,resolve,isAbsolute,dirname} from 'node:path';
import {readFile} from 'node:fs/promises';
export function locations(options={}){
  const home=process.env.DSH_HOME||join(homedir(),'.dsh');
  const data=resolve(options.dataDir||(options.configFile?dirname(options.configFile):join(home,'singing')));
  const settings={};
  if(options.referenceAudio?.trim()){if(!isAbsolute(options.referenceAudio.trim()))throw Error('参考音频请填写绝对路径');settings.referenceAudio=options.referenceAudio.trim()}
  for(const [key,min,max] of [['voiceGain',.1,3],['musicGain',.05,2],['harmonyGain',0,1.5]]){
    if(options[key]===undefined)continue;
    if(!Number.isFinite(options[key])||options[key]<min||options[key]>max)throw Error('无效唱歌设置：'+key);
    settings[key]=options[key];
  }
  for(const key of ['autoOctave','shortenGaps']){if(options[key]===undefined)continue;if(typeof options[key]!=='boolean')throw Error('无效唱歌设置：'+key);settings[key]=options[key]}
  const durations={};for(const [key,fallback] of [['excerptSeconds',45],['longSeconds',90]]){const value=options[key]??fallback;if(!Number.isFinite(value)||value<5||value>3600)throw Error('默认片段时长需为5到3600秒');durations[key]=value}
  return {dataDir:data,configFile:resolve(options.configFile||join(data,'backend.json')),python:options.pythonPath||join(data,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python'),delivery:options.delivery||'auto',timeoutMs:options.timeoutMs??0,settings,...durations};
}
export async function backendOutput(configFile){
  let config;try{config=JSON.parse(await readFile(configFile,'utf8'))}catch{throw Error('唱歌后端未配置，请先运行安装脚本并设置参考音频')}
  const base=dirname(configFile),data=resolve(base,config.dataDir||'.');
  return isAbsolute(config.outputDir||'')?resolve(config.outputDir):resolve(base,config.outputDir||join(data,'output'));
}
