import test from 'node:test';import assert from 'node:assert/strict';
import {locations} from '../lib/config.js';import {validate} from '../lib/action.js';
import {runBackend} from '../lib/runner.js';import {EventEmitter} from 'node:events';
test('plugin durations affect defaults, but never explicit durations or full songs',()=>{
 const config=locations({excerptSeconds:25,longSeconds:65});
 assert.equal(validate({song:'test'},config).duration,25);assert.equal(validate({song:'test',mode:'long'},config).duration,65);
 assert.equal(validate({song:'test',duration_seconds:180},config).duration,180);assert.equal(validate({song:'test',mode:'full'},config).duration,null);
 assert.equal(validate({song:'test',start_seconds:30},config).duration,null);
});
test('plugin settings reject invalid values and forward only supported controls',()=>{
 for(const options of [{voiceGain:NaN},{musicGain:0},{harmonyGain:-1},{autoOctave:'false'},{referenceAudio:'relative.wav'},{excerptSeconds:0}])assert.throws(()=>locations(options));
 const config=locations({autoOctave:false,musicGain:.4,untrustedValue:'ignored'});
 assert.deepEqual(config.settings,{autoOctave:false,musicGain:.4});
});
test('settings reach the Python worker without shell arguments or rewriting backend files',async()=>{
 const config=locations({autoOctave:false,shortenGaps:false,voiceGain:1.4});let captured;
 const result=await runBackend('request.json',config,undefined,{spawnProcess:(_python,_args,options)=>{
   captured=options;const child=new EventEmitter();child.stdout=new EventEmitter();child.stderr=new EventEmitter();child.stdout.setEncoding=child.stderr.setEncoding=()=>{};
   queueMicrotask(()=>{child.stdout.emit('data',JSON.stringify({ok:true,cacheMiss:true}));child.emit('close',0)});return child;
 }});
 assert.equal(result.cacheMiss,true);assert.equal(captured.shell,false);assert.deepEqual(JSON.parse(captured.env.DSH_SINGING_UI_SETTINGS),config.settings);
});
