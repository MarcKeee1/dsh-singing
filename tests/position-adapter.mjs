import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {singingAction} from '../integrations/dsh-onebot-qq/lib/sing-song.js';
const exec={agent:{session:{id:'onebot-group-100000002',header:{cwd:'C:/dsh-test-workspace'}}},signal:new AbortController().signal};
let sent=0,runs=0;const requests=[];
const bridge={deps:{policy:{adminUsers:['100000001']}},connected:true,chatForSession:()=> 'group:100000002',mediaSendRoots:async()=>({roots:['C:/Users/Example/.dsh/media/onebot'],isTurnAdmin:false}),sendSegments:async()=>{sent++;return 'stub'}};
const run=async(file)=>{runs++;const req=JSON.parse(await readFile(file,'utf8'));requests.push(req);return {ok:true,path:req.output,seconds:20,quality:{passed:true},cacheHit:true,sourceInfo:{artist:'周杰伦',sourceStartSeconds:req.start,positionRequest:{mode:'seconds'}}}};
const action=singingAction(bridge,{},async()=> 'base64://YQ==',run);
for(const start of [undefined,0,80,80.25]){
 const r=await action({song:'搁浅',artist:'周杰伦',start_seconds:start},exec);assert.equal(r.ok,true,r.error);
 assert.equal(requests.at(-1).start,start??null);assert.equal(requests.at(-1).positionVersion,1);
}
const lyric=await action({song:'搁浅',artist:'周杰伦',chorus_hint:'小鲸鱼在海里',lyric_occurrence:2},exec);
assert.equal(lyric.ok,true);assert.equal(requests.at(-1).lyric_occurrence,2);assert.equal(requests.at(-1).start,null);
const before=runs;
for(const args of [{start_seconds:0,chorus_hint:'小鲸鱼在海里'},{start_seconds:-1},{start_seconds:Infinity},{chorus_hint:'短'},{chorus_hint:'小鲸鱼在海里',lyric_occurrence:1.5},{lyric_occurrence:2}]){
 const r=await action({song:'搁浅',artist:'周杰伦',...args},exec);assert.equal(r.ok,false);
}
assert.equal(runs,before);assert.equal(sent,5);
console.log(JSON.stringify({passed:11,zeroPreserved:true,omissionPreserved:true,publicSecondsForwarded:true,conflictsRejectedBeforeWorker:true,qqSent:false}));
