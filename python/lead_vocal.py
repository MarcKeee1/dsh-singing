"""Content-addressed, isolated lead/harmony extraction before single-F0 conversion."""
import hashlib,json,pathlib,shutil,subprocess,sys

VERSION=1
MODEL_SHA='bf32e15105a09c0f7dddd2b67346146334d6f3ecb399ed7638eba2ab07cbf5f4'
def digest(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def valid(folder,source_hash):
    import soundfile as sf
    try:
        meta=json.loads((folder/'lead.json').read_text(encoding='utf-8'))
        lead=folder/'lead.wav'
        return (not lead.is_symlink() and meta['version']==VERSION and meta['sourceSha256']==source_hash
                and meta['modelSha256']==MODEL_SHA and meta['leadSha256']==digest(lead)
                and sf.info(lead).samplerate==44100 and abs(sf.info(lead).duration-meta['seconds'])<.001)
    except (OSError,ValueError,KeyError,RuntimeError):return False

def prepare(root,source,destination,code_dir=None):
    root=pathlib.Path(root);source=pathlib.Path(source);destination=pathlib.Path(destination)
    code_dir=pathlib.Path(code_dir or __file__).resolve()
    if code_dir.is_file():code_dir=code_dir.parent
    source_hash=digest(source)
    key=hashlib.sha256((source_hash+MODEL_SHA+str(VERSION)).encode()).hexdigest()
    cache=root/'lead-cache'/key;destination.mkdir(parents=True,exist_ok=True)
    hit=valid(cache,source_hash)
    if hit:
        for name in ('lead.wav','lead.json'):shutil.copyfile(cache/name,destination/name)
    else:
        from runtime import CONFIG
        python=CONFIG['leadPython']
        if not python.is_file():raise RuntimeError('Lead-vocal environment is missing')
        import soundfile as sf
        subprocess.run([str(python),str(code_dir/'lead_worker.py'),'--source',str(source),'--output',str(destination)],
                       check=True,timeout=max(180,sf.info(source).duration*5),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if not valid(destination,source_hash):raise RuntimeError('Lead-vocal validation failed')
        cache.mkdir(parents=True,exist_ok=True)
        for name in ('lead.wav','lead.json'):
            temp=cache/(name+'.tmp');shutil.copyfile(destination/name,temp);temp.replace(cache/name)
    meta=json.loads((destination/'lead.json').read_text(encoding='utf-8'));meta['cacheHit']=hit
    return destination/'lead.wav',meta
