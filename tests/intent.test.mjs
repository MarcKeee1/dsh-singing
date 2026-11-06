import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {explicitFull,protectFullIntent,incomingText} from '../lib/intent.js';
test('all full-song phrases override a model-supplied ninety seconds',async()=>{
 for(const text of ['唱 Test 完整版','唱完整版本','把整首唱完','全部唱完','从头到尾唱','为什么完整版只唱90秒，不是我要的']){
  assert.equal(explicitFull(text),true,text);const r=await protectFullIntent({song:'Test',mode:'long',duration_seconds:90},text,{});assert.equal(r.mode,'full');assert.equal(r.duration_seconds,undefined);
 }
});
test('explicit excerpts and starts retain the user request',()=>{
 for(const text of ['不要完整版，唱长一点','完整版太长，先唱副歌','完整版只唱90秒','唱完整版中的开头，先唱30秒','从30秒开始唱到结尾','这次90秒就行','唱《完整版》的一段'])assert.equal(explicitFull(text),false,text);
});
test('a short cached recording never satisfies explicit full intent',async t=>{
 const root=await mkdtemp(join(tmpdir(),'full-intent-'));t.after(()=>rm(root,{recursive:true,force:true}));await mkdir(join(root,'performance-cache'));
 const id='a'.repeat(64),file=join(root,'performance-cache',id+'.json');const r={ok:true,quality:{passed:true},sourceInfo:{sourceProvider:'bilibili',song:'Test',artist:'Singer',sourceComplete:false}};await writeFile(file,JSON.stringify(r));
 const args=await protectFullIntent({cache_id:id},'唱Test完整版',{dataDir:root});assert.equal(args.cache_id,undefined);assert.equal(args.song,'Test');assert.equal(args.mode,'full');
 r.sourceInfo.sourceComplete=true;await writeFile(file,JSON.stringify(r));assert.deepEqual(await protectFullIntent({cache_id:id},'全部唱完',{dataDir:root}),{cache_id:id});
});
test('inbound text uses actual user content',()=>{assert.equal(incomingText([{type:'text',text:'<user_message sender="x">唱完整版</user_message>'}]),'唱完整版');assert.equal(incomingText([{type:'text',text:'唱整首'}]),'唱整首')});
test('missing or legacy event content never breaks a session',()=>{assert.equal(incomingText(undefined),'');assert.equal(incomingText({}), '');assert.equal(incomingText('唱完整版'),'唱完整版')});
