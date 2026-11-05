import test from 'node:test';import assert from 'node:assert/strict';import {EventEmitter} from 'node:events';import {PassThrough} from 'node:stream';
import {withLocalGpu} from '../lib/queue.js';import {runBackend} from '../lib/runner.js';import {locations} from '../lib/config.js';
test('cancelled queued work returns promptly and never launches',async()=>{
  let release,called=false;const first=withLocalGpu(()=>new Promise(r=>release=r));await new Promise(r=>setImmediate(r));
  const c=new AbortController();const second=withLocalGpu(()=>{called=true},c.signal);c.abort();
  await assert.rejects(second);release();await first;await new Promise(r=>setImmediate(r));assert.equal(called,false);
});
test('default config removes total generation timeout',()=>{assert.equal(locations().timeoutMs,0);assert.equal(locations({timeoutMs:60000}).timeoutMs,60000)});
function child(){const c=new EventEmitter();c.stdout=new PassThrough();c.stderr=new PassThrough();return c}
test('backend uses hidden no-shell process and accepts a cache result',async()=>{
  const c=child();const result=runBackend('request.json',{python:'python',configFile:'backend.json',timeoutMs:0},new AbortController().signal,{spawnProcess:(bin,args,options)=>{
    assert.equal(options.shell,false);assert.equal(options.windowsHide,true);assert.equal(options.env.DSH_SINGING_CONFIG,'backend.json');
    process.nextTick(()=>{c.stdout.write('{"ok":true,"cacheMiss":true}');c.emit('close',0)});return c;
  }});assert.equal((await result).cacheMiss,true);
});
test('backend rejects malformed output and startup failures',async()=>{
  for(const startup of [false,true]){
    const c=child();await assert.rejects(runBackend('x',{python:'x',configFile:'x',timeoutMs:0},undefined,{spawnProcess:()=>{process.nextTick(()=>{if(startup)c.emit('error',Error('ENOENT'));else{c.stdout.write('invalid');c.emit('close',0)}});return c}}));
  }
});
