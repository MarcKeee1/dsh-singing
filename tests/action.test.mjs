import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {validate,createAction} from '../lib/action.js';

test('request validation preserves the selected singer and distinguishes zero from omission',()=>{
  assert.equal(validate({song:'Test',artist:'Cover artist',start_seconds:0}).start,0);
  assert.equal(validate({song:'Test',artist:'Original'}).start,null);
  for(const bad of [{duration_seconds:NaN},{start_seconds:-1},{chorus_hint:'ab'},{chorus_hint:'four words',start_seconds:0},{lyric_occurrence:2},{source_url:'https://b23.tv/test',source_path:'/tmp/a.wav'}])assert.throws(()=>validate({song:'Test',artist:'Artist',...bad}));
});

async function fixture(t,delivery='auto'){
  const root=await mkdtemp(join(tmpdir(),'dsh-singing-test-'));t.after(()=>rm(root,{recursive:true,force:true}));
  const output=join(root,'output');await mkdir(output);const configFile=join(root,'backend.json');await writeFile(configFile,JSON.stringify({dataDir:root,outputDir:output}));
  let reads=0,sends=0;const tools={get:()=>({name:'qq_send_voice'}),execute:async input=>{sends++;assert.deepEqual(Object.keys(input.arguments),['path']);assert.ok(input.parent);return {isError:false,value:{sent:true,messageId:'fixture'}}}};
  const agent={session:{id:'onebot-group-10001'},ctx:{tools}},turns=new Map([[agent.session.id,{turn:1,deliveries:new Map()}]]),config={dataDir:root,configFile,delivery};
  const run=async file=>{reads++;const request=JSON.parse(await readFile(file,'utf8'));await writeFile(request.output,'mock audio');return {ok:true,path:request.output,seconds:10,quality:{passed:true},cacheHit:true}};
  const exec={agent,token:Symbol('parent'),callId:'root',signal:new AbortController().signal};
  return {tools,agent,turns,config,run,exec,action:createAction({tools},config,turns,{run}),counts:()=>({reads,sends})};
}
const args={song:'A song',artist:'Selected performer'};
test('full song and from-position requests have no 90-second ceiling',()=>{
  assert.equal(validate(args).duration,45);
  assert.equal(validate({...args,mode:'long'}).duration,90);
  assert.equal(validate({...args,mode:'long',duration_seconds:65}).duration,65);
  assert.equal(validate({...args,mode:'full'}).mode,'full');
  assert.equal(validate({...args,mode:'full'}).duration,null);
  assert.equal(validate({...args,duration_seconds:400}).duration,400);
  assert.equal(validate({...args,start_seconds:80}).mode,'from');
  assert.equal(validate({...args,start_seconds:80}).duration,null);
  for(const bad of [{mode:'full',duration_seconds:20},{mode:'full',start_seconds:0},{mode:'chorus',start_seconds:1},{mode:'from'},{mode:'other'}])assert.throws(()=>validate({...args,...bad}));
});
test('a verified full song longer than 90 seconds can be delivered',async t=>{
  const f=await fixture(t);const action=createAction({tools:f.tools},f.config,f.turns,{run:async(...a)=>({...await f.run(...a),seconds:240})});
  assert.equal((await action({...args,mode:'full'},f.exec)).delivery,'sent');assert.equal(f.counts().sends,1);
});
test('QQ uses the registry and only the current chat; same-turn repeat sends once',async t=>{
  const f=await fixture(t);const first=await f.action(args,f.exec),second=await f.action(args,f.exec);
  assert.equal(first.delivery,'sent');assert.equal(second.duplicateSuppressed,true);assert.equal(f.counts().sends,1);assert.equal(f.counts().reads,1);
});
test('an uncertain send is not automatically retried',async t=>{
  const f=await fixture(t);let attempts=0;f.tools.execute=async()=>{attempts++;throw Error('connection lost')};
  assert.equal((await f.action(args,f.exec)).delivery,'unknown');assert.equal((await f.action(args,f.exec)).duplicateSuppressed,true);assert.equal(attempts,1);
});
test('file mode never calls a QQ tool',async t=>{
  const f=await fixture(t,'file');const result=await f.action(args,f.exec);assert.equal(result.delivery,'file');assert.ok(result.path.endsWith('.mp3'));assert.equal(f.counts().sends,0);
});
test('QQ tool missing fails before any expensive generation',async t=>{
  const f=await fixture(t);f.tools.get=()=>undefined;const result=await f.action(args,f.exec);assert.equal(result.ok,false);assert.equal(f.counts().reads,0);
});
test('failed pitch QA does not send',async t=>{
  const f=await fixture(t);const action=createAction({tools:f.tools},f.config,f.turns,{run:async(...a)=>({...await f.run(...a),quality:{passed:false}})});
  assert.equal((await action(args,f.exec)).ok,false);assert.equal(f.counts().sends,0);
});
test('cache miss enters the shared queue once',async t=>{
  const f=await fixture(t);let queued=0;const action=createAction({tools:f.tools},f.config,f.turns,{run:async(file,c,s,o)=>o?.cacheOnly?{ok:true,cacheMiss:true}:f.run(file),queue:async job=>{queued++;return job()}});
  assert.equal((await action(args,f.exec)).delivery,'sent');assert.equal(queued,1);
});
test('cancellation before start has no side effects',async t=>{
  const f=await fixture(t),controller=new AbortController();controller.abort();assert.equal((await f.action(args,{...f.exec,signal:controller.signal})).ok,false);assert.equal(f.counts().reads,0);
});
test('source identity includes the artist and position',()=>{
  assert.notDeepEqual(validate({song:'Same',artist:'A'}),validate({song:'Same',artist:'B'}));
  assert.notDeepEqual(validate({song:'Same',artist:'A'}),validate({song:'Same',artist:'A',start_seconds:0}));
});
