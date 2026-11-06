import z from '@deepseek-ai/schemastery';
import {defineTool} from '@deepseek-ai/dsh-tools';
import {locations} from './config.js';
import {createAction} from './action.js';
export const name='dsh-singing',inject=['tools'];
export const Config=z.object({
  referenceAudio:z.string().default('').description('参考音色录音的绝对路径；建议10–20秒干净人声。留空沿用后端配置，不需要每次调用语音API'),
  excerptSeconds:z.number().min(5).max(3600).default(45).description('普通点歌默认秒数；用户明确要求的时长和完整版不受此值限制'),
  longSeconds:z.number().min(5).max(3600).default(90).description('“唱长一点”默认秒数；完整版仍唱到结尾'),
  autoOctave:z.boolean().default(true).description('自动判断八度：低音占多数时按参考音域升八度；关闭后按原曲音域唱'),
  voiceGain:z.number().min(.1).max(3).step(.05).default(1.25).description('人声音量倍率'),
  musicGain:z.number().min(.05).max(2).step(.05).default(.55).description('伴奏音量倍率'),
  harmonyGain:z.number().min(0).max(1.5).step(.05).default(.8).description('独立和声相对音量；0为静音。保留尾音时间，不拼接两条声部'),
  shortenGaps:z.boolean().default(true).description('保守缩短长间奏；关闭后保留原曲间奏时长'),
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
    description:`用户明确点歌时调用。歌手可省略：自动搜索尽量找原唱；只有其他或未确认版本时工具返回needsConfirmation，先问用户，同意后才传对应source_url。用户给具体视频链接时直接按该视频，不要求标题标歌名或歌手，简介里的歌手署名也可用于自动原唱匹配。使用配置音色按原曲旋律演唱。mode=opening只唱开头段；chorus只唱副歌；opening_to_chorus从起唱处到第一遍完整副歌结束；long唱长一点，默认约${config.longSeconds}秒，不自动延长到两分钟或整首；只有用户明确说整首、全部唱完或完整版时才用full。普通点歌用excerpt，默认约${config.excerptSeconds}秒；用户只说长一点时填long且不填duration_seconds。明确指定时长则按指定值；from从用户指定歌词或秒数开始，未给时长则唱到结尾。${config.excerptSeconds}/${config.longSeconds}秒是默认片段长度，完整版仍不设歌长上限。已缓存整首时，副歌和指定片段从完整歌声剪切，不重新合成。秒数按未删间奏的原曲时间；长间奏在播放版中保守缩短。先复用同音色同版本成品，再按B站、网易云、QQ音乐顺序查原曲；明确提供链接时只使用该版本，访问失败不绕过限制。歌词起句至少四字、与秒数互斥，lyric_occurrence指定第几次。不会擅换歌手、不会把无法定位的普通片段说成副歌。delivery=sent时只保留已经发出的音频，本回合不要再说放了第几首、歌名确认或旧音色提醒，也不要补文字，不再重发；unknown送达未确认，不自动重试；file为本地文件。失败会自动提供缓存歌单，playlistDelivery=sent时不复述列表；用户选第几首时从上次catalog.items取cacheId，调用cache_id直接播放，不重新查找或合成。list_cache=true可主动查看。失败说明实际阶段，不用朗读歌词冒充歌声。`,
    parameters:{song:{type:'string',description:'自动找歌填歌名；具体链接或缓存选择可省略'},artist:{type:'string',description:'可选，用户指定歌手才填写；不要因为没写歌手拒绝点歌'},mode:{type:'string',enum:['full','chorus','from','excerpt','opening','opening_to_chorus','long'],description:'用户说全部唱完、整首、完整版时必须填full且不填duration_seconds；opening开头；chorus副歌；opening_to_chorus开头到完整副歌；long较长片段；from指定起点；excerpt普通片段'},cache_id:{type:'string',description:'用户选择缓存歌单时，传对应条目的cacheId；不再搜索或重新合成'},list_cache:{type:'boolean',description:'true查看已经唱好的歌单；用户选序号时从上次歌单取对应cacheId'},cache_offset:{type:'number',description:'更多缓存歌曲时传上次nextOffset，默认0'},source_url:{type:'string',description:'用户提供的B站BV/b23.tv、网易云单曲或QQ音乐单曲链接'},source_path:{type:'string',description:'管理员allowedSourceRoots内的本地音频'},duration_seconds:{type:'number',description:'仅用户明确指定时填写，至少5秒，无90秒上限；full不填，from省略则唱到结束'},start_seconds:{type:'number',description:'原曲起点秒数，与chorus_hint互斥'},chorus_hint:{type:'string',description:'用户给出的起唱歌词至少四字，不能自造'},lyric_occurrence:{type:'number',description:'起句第几次，默认1，最多10'}},
    ...(config.timeoutMs>0?{timeoutMs:config.timeoutMs+30_000}:{}),isConcurrencySafe:()=>false,
    output:{schema:{type:'json'},render:(_args,result)=>[{type:'text',text:JSON.stringify(result)}]},
    execute:createAction(ctx,config,turns),
  }));
}
