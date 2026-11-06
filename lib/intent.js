import {readFile} from 'node:fs/promises';
import {join} from 'node:path';

export function explicitFull(text=''){
 let clean=String(text).replace(/《[^》]*》|〈[^〉]*〉/g,'').replace(/(?:不要|别|不想|不是|不必|不用)(?:再)?(?:只)?(?:唱|听)?(?:完整版|完整版本|整首|全曲)/g,'');
 if(/(?:只|就|先)(?:唱|听|放).{0,8}(?:副歌|开头|片段)/.test(clean))return false;
 if(/从.{0,24}(?:秒|分钟|歌词|这句).{0,8}(?:开始|唱)/.test(clean))return false;
 const n='[\\d零一二三四五六七八九十百两]+(?:\\.\\d+)?';
 clean=clean.replace(new RegExp('(?:不要|别|不想|不用)(?:只)?(?:唱|听|放)\\s*'+n+'\\s*(?:秒|分钟|分半)','g'),'');
 if(/(?:为什么|怎么|为何).{0,24}(?:完整版|整首).{0,12}(?:只有|只唱|只放)/.test(clean))return true;
 if(new RegExp('(?:只|就|先)?(?:唱|听|放)(?:个|一段|大约|约)?\\s*'+n+'\\s*(?:秒|分钟|分半)').test(clean)||new RegExp(n+'\\s*(?:秒|分钟|分半)(?:就行|即可|够了)').test(clean))return false;
 return /完整版|完整版本|整首|全曲|全部唱完|唱完整|唱完这首|从头到尾/.test(clean);
}

export function incomingText(content=[]){
 const blocks=Array.isArray(content)?content:typeof content==='string'?[{type:'text',text:content}]:[];
 return blocks.filter(x=>x?.type==='text').map(x=>{const t=String(x.text||'');const hits=[...t.matchAll(/<user_message\b[^>]*>([\s\S]*?)<\/user_message>/g)];return hits.length?hits.map(m=>m[1].trim()).join('\n'):t;}).join('\n');
}

export async function protectFullIntent(args,text,config){
 if(args.list_cache===true||!explicitFull(text))return args;
 const next={...args};
 if(next.cache_id){
  if(!/^[0-9a-f]{64}$/.test(next.cache_id))throw Error('缓存歌曲编号无效');
  let record;try{record=JSON.parse(await readFile(join(config.dataDir,'performance-cache',next.cache_id+'.json'),'utf8'))}catch{throw Error('用户要求整首，所选缓存不可用；请用歌名和 mode=full 生成，不能改播短片段')}
  const source=record.sourceInfo||{};
  if(!record.ok||!record.quality?.passed||source.sourceProvider==='local'||!source.song||!source.artist)throw Error('所选缓存不能用于定位完整版，请用歌名和 mode=full');
  if(source.sourceComplete===true)return {cache_id:next.cache_id};
  next.song=source.song;next.artist=source.artist;if(source.sourcePage)next.source_url=source.sourcePage;delete next.cache_id;
 }
 for(const key of ['duration_seconds','start_seconds','chorus_hint','lyric_occurrence'])delete next[key];
 return {...next,mode:'full'};
}
