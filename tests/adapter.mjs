import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {singingAction} from '../integrations/dsh-onebot-qq/lib/sing-song.js';
import {withLocalGpu} from '../integrations/dsh-onebot-qq/lib/local-gpu-queue.js';

const make=()=>{
 const sent=[];let chat='group:100000002';
 const bridge={deps:{policy:{adminUsers:['100000001']}},connected:true,chatForSession:()=>chat,
   mediaSendRoots:async()=>({roots:['C:/Users/Example/.dsh/media/onebot'],isTurnAdmin:false}),
   sendSegments:async(target,segments)=>{sent.push({target,segments});return 123;}};
 const exec={agent:{session:{id:'onebot-group-100000002',header:{cwd:'C:/dsh-test-workspace'}}},signal:new AbortController().signal};
 const run=async file=>{const req=JSON.parse(await readFile(file,'utf8'));assert.equal(req.duration,null);return {ok:true,path:req.output,seconds:16,quality:{passed:true}}};
 return {bridge,exec,sent,run,changeChat:()=>{chat='group:999';}};
};
const read=async()=> 'base64://ZmFrZQ==';let count=0;
{
 const t=make();let called=false;
 const r=await singingAction(t.bridge,{},read,async()=>{called=true;throw Error('must not run');})({song:'搁浅'},t.exec);
 assert.equal(r.ok,false);assert.match(r.error,/原唱歌手/);assert.equal(called,false);assert.equal(t.sent.length,0);count++;
}
{
 const t=make(),r=await singingAction(t.bridge,{maxVoiceBytes:10e6},read,t.run)({song:'无人之岛',artist:'任然'},t.exec);
 assert.equal(r.ok,true);assert.equal(t.sent.length,1);assert.equal(t.sent[0].target,'group:100000002');count++;
}
{
 const t=make();t.exec.agent.session.header.cwd='E:/unrelated';
 const r=await singingAction(t.bridge,{},read,t.run)({song:'无人之岛',artist:'任然'},t.exec);assert.equal(r.ok,false);assert.equal(t.sent.length,0);count++;
}
{
 const t=make(),r=await singingAction(t.bridge,{},read,t.run)({song:'x',artist:'Tester',source_path:'C:/secret.wav'},t.exec);
 assert.equal(r.ok,false);assert.equal(t.sent.length,0);count++;
}
{
 const t=make(),r=await singingAction(t.bridge,{},read,t.run)({song:'x',artist:'Tester',duration_seconds:91},t.exec);
 assert.equal(r.ok,false);assert.equal(t.sent.length,0);count++;
}
{
 const t=make(),r=await singingAction(t.bridge,{},read,async file=>{const r=await t.run(file);r.quality.passed=false;return r;})({song:'x',artist:'Tester'},t.exec);
 assert.equal(r.ok,false);assert.equal(t.sent.length,0);count++;
}
{
 const t=make(),r=await singingAction(t.bridge,{},read,async file=>{const r=await t.run(file);t.changeChat();return r;})({song:'x',artist:'Tester'},t.exec);
 assert.equal(r.ok,false);assert.equal(t.sent.length,0);count++;
}
{
 const t=make();let attempts=0;t.bridge.sendSegments=async()=>{attempts++;throw Error('ack timeout');};
 const r=await singingAction(t.bridge,{},read,t.run)({song:'x',artist:'Tester'},t.exec);
 assert.equal(r.delivery,'unknown');assert.equal(attempts,1);count++;
}
{
 const t=make(),abort=new AbortController();abort.abort();t.exec.signal=abort.signal;
 const r=await singingAction(t.bridge,{},read,t.run)({song:'x',artist:'Tester'},t.exec);assert.equal(r.ok,false);assert.equal(t.sent.length,0);count++;
}
{
 const order=[];let release;const gate=new Promise(resolve=>release=resolve);
 const first=withLocalGpu(async()=>{order.push('first-start');await gate;order.push('first-end');});
 const second=withLocalGpu(async()=>order.push('second'));
 await new Promise(resolve=>setTimeout(resolve,5));assert.deepEqual(order,['first-start']);release();await Promise.all([first,second]);
 assert.deepEqual(order,['first-start','first-end','second']);count++;
}
console.log(JSON.stringify({passed:count,checks:'current-chat routing, workspace fence, admin file import, 90s cap, pitch rejection, changed session, uncertain delivery, cancellation, shared GPU queue'}));
