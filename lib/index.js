import z from '@deepseek-ai/schemastery';
import {defineTool} from '@deepseek-ai/dsh-tools';
import {locations} from './config.js';
import {createAction} from './action.js';
export const name='dsh-singing',inject=['tools'];
export const Config=z.object({
  dataDir:z.string().default('').description('后端数据目录；默认 DSH_HOME/singing 或 ~/.dsh/singing'),
  configFile:z.string().default('').description('backend.json 绝对路径；默认数据目录下'),
  pythonPath:z.string().default('').description('后端虚拟环境 Python；默认数据目录下 .venv'),
  delivery:z.union([z.const('auto'),z.const('file'),z.const('qq')]).default('auto').description('auto：QQ 会话通过已有 qq_send_voice 发送，桌面会话返回文件；file：仅生成文件'),
  toolName:z.string().default('sing_song').description('避免与已有唱歌插件重复注册，可改为 sing_song_local'),
  timeoutMs:z.number().min(0).max(2147400000).default(0).description("总处理超时；0表示不设总超时，取消仍有效"),
});
export function apply(ctx,options){
  const config=locations(options),turns=new Map();
  const toolName=options.toolName||'sing_song';if(!/^[a-z][a-z0-9_]{1,63}$/.test(toolName))throw Error('Invalid singing tool name');
  if(ctx.tools.get(toolName))throw Error('A singing tool with this name already exists; disable it or set toolName to sing_song_local');
  ctx.on('agent/inbox/claimed',({agent,turn})=>{const id=String(agent?.session?.id||'');if(id&&turns.get(id)?.turn!==turn)turns.set(id,{turn,deliveries:new Map()})});
  ctx.on('session/event',(session,event)=>{if(event?.type==='turn/end')turns.delete(String(session.id))});
  ctx.on('session/disposed',session=>turns.delete(String(session.id)));
  ctx.tools.register(defineTool({
    name:toolName,
    description:'用户明确点歌时调用，使用配置音色按原曲旋律演唱。mode=full唱整首；chorus只唱识别到的副歌；from从用户指定歌词或秒数开始，未给时长则唱到结尾；excerpt默认约45秒普通片段。没有90秒上限。已缓存整首时，副歌和指定片段从完整歌声剪切，不重新合成。秒数按未删间奏的原曲时间；长间奏在播放版中保守缩短。先复用同音色同版本成品，再按B站、网易云、QQ音乐顺序查原曲；明确提供链接时只使用该版本，访问失败不绕过限制。歌词起句至少四字、与秒数互斥，lyric_occurrence指定第几次。不会擅换歌手、不会把无法定位的普通片段说成副歌。delivery=sent已发一次，不再重发；unknown送达未确认，不自动重试；file为本地文件。失败说明实际阶段，不用朗读歌词冒充歌声。',
    parameters:{song:{type:'string',required:true,description:'准确歌名'},artist:{type:'string',required:true,description:'指定歌手或版本演唱者'},mode:{type:'string',enum:['full','chorus','from','excerpt'],description:'full整首；chorus副歌；from指定起点；excerpt普通片段'},source_url:{type:'string',description:'用户提供的B站BV/b23.tv、网易云单曲或QQ音乐单曲链接'},source_path:{type:'string',description:'管理员allowedSourceRoots内的本地音频'},duration_seconds:{type:'number',description:'可选片段时长，至少5秒，无歌长上限；full不填，from省略则唱到结束'},start_seconds:{type:'number',description:'原曲起点秒数，与chorus_hint互斥'},chorus_hint:{type:'string',description:'用户给出的起唱歌词至少四字，不能自造'},lyric_occurrence:{type:'number',description:'起句第几次，默认1，最多10'}},
    ...(config.timeoutMs>0?{timeoutMs:config.timeoutMs+30_000}:{}),isConcurrencySafe:()=>false,
    output:{schema:{type:'json'},render:(_args,result)=>[{type:'text',text:JSON.stringify(result)}]},
    execute:createAction(ctx,config,turns),
  }));
}
