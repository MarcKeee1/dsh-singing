import {randomUUID} from 'node:crypto';import {mkdir,writeFile} from 'node:fs/promises';import {join} from 'node:path';
import {formatCatalog,catalogSegments} from './catalog-format.js';

export async function showCatalog(ctx,config,turns,args,exec,run,{failure=false}={}){
  exec.signal?.throwIfAborted();const agent=exec.agent,session=String(agent?.session?.id||'');
  if(!session)throw Error('需要当前会话');
  const offset=args.cache_offset??0;if(!Number.isInteger(offset)||offset<0)throw Error('歌单分页位置无效');
  const state=turns.get(session)?.deliveries,key='cache-catalog:'+offset;
  if(state?.has(key))return {...state.get(key),duplicateSuppressed:true};
  const directory=join(config.dataDir,'requests');await mkdir(directory,{recursive:true});
  const file=join(directory,randomUUID()+'.json');await writeFile(file,JSON.stringify({catalog:true,catalogOffset:offset}),{flag:'wx'});
  const catalog=await run(file,config,exec.signal,{cacheOnly:true});exec.signal?.throwIfAborted();
  if(catalog.kind!=='cached_song_catalog'||!Array.isArray(catalog.items))throw Error('缓存歌单结果无效');
  const text=formatCatalog(catalog,{failure}),service=agent.ctx?.tools||ctx.tools;
  const value={catalog,catalogText:text,playlistDelivery:'reply',note:'请把 catalogText 作为本次文字回复；选择歌曲时用对应 cacheId 调用 sing_song 的 cache_id，不重新搜索。'};
  const isQQ=/^onebot-(?:group|private)-/.test(session),send=config.delivery!=='file'&&isQQ&&service.get('qq_send_segments',agent);
  if(send){
    if(String(agent.session.id)!==session)throw Error('当前会话已变化');
    value.playlistDelivery='unknown';value.note='歌单发送结果不确定，不自动重发。';state?.set(key,value);
    try{
      const sent=await service.execute({name:'qq_send_segments',arguments:{segments:catalogSegments(text),intervalMs:0},agent,signal:exec.signal,parent:exec.token,callId:randomUUID(),rootCallId:exec.rootCallId||exec.callId});
      if(sent.isError||sent.value?.sent!==true)return value;
      value.playlistDelivery='sent';value.note='缓存歌单已发送，不要重复复述列表。等用户选歌，再用对应 cacheId 调用 sing_song 的 cache_id；不联网、不合成，也不要自己选一首播放。';
    }catch{return value}
  }
  state?.set(key,value);return value;
}
