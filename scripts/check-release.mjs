import {readdir,readFile,stat} from 'node:fs/promises';import {resolve,relative,join} from 'node:path';import {fileURLToPath} from 'node:url';
const root=resolve(fileURLToPath(new URL('..',import.meta.url)));const errors=[];let count=0;
const ignored=new Set(['.git','__pycache__','node_modules']);
const allowed=new Set(['.github','lib','python','scripts','tests','docs','licenses','vendor-overrides','.gitignore','.gitattributes','LICENSE','NOTICE','README.md','README.en.md','CHANGELOG.md','package.json','cordis.patch.yml','models.lock.json','vendor.lock.json','requirements.txt','requirements-test.txt','constraints.txt','backend.example.json']);
const privatePath=new RegExp('(?:[CE]:[/\\\\](?:Users[/\\\\][^/\\\\]+|dsh-singing|voice-local|Codex))','i');
async function walk(dir){for(const entry of await readdir(dir,{withFileTypes:true})){
  if(ignored.has(entry.name))continue;const path=join(dir,entry.name),name=relative(root,path).replaceAll('\\','/');
  if(!allowed.has(name.split('/')[0])){errors.push('Unexpected release item: '+name);continue}
  if(entry.isSymbolicLink()){errors.push('Symlink in source: '+name);continue}
  if(entry.isDirectory()){await walk(path);continue}
  count++;const info=await stat(path);if(info.size>1024*1024){errors.push('Unexpected large file: '+name);continue}
  if(/\.(mp3|wav|flac|pth|pt|safetensors|db|sqlite|log|jsonl|tgz|zip|pyc)$/i.test(name))errors.push('Private/generated binary: '+name);
  const text=await readFile(path,'utf8');
  if(privatePath.test(text))errors.push('Personal machine path: '+name);
  if(/(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{25,}|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----)/.test(text))errors.push('Credential pattern: '+name);
  if(name.endsWith('.md'))for(const m of text.matchAll(/\]\(([^)#]+)(?:#[^)]*)?\)/g)){
    if(/^(?:https?:|mailto:)/.test(m[1]))continue;
    try{await stat(resolve(dir,m[1]))}catch{errors.push('Broken local documentation link: '+name+' -> '+m[1])}
  }
}}
await walk(root);
const pkg=JSON.parse(await readFile(join(root,'package.json'),'utf8'));
if(pkg.name!=='dsh-singing'||pkg.license!=='GPL-3.0-only')errors.push('Unexpected package identity/license');
if(errors.length){console.error(errors.join('\n'));process.exitCode=1}else console.log(`Release check passed: ${count} source files; no runtime audio, models, personal paths or credential patterns.`);
