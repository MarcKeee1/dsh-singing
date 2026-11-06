"""Reuse exact separated stems, independently of singing voice and request mode."""
import hashlib,json,os,pathlib,re,shutil,tempfile
VERSION='htdemucs-shifts0-segment7-v1'
NAMES=('vocals.wav','no_vocals.wav')
def digest(file):return hashlib.sha256(pathlib.Path(file).read_bytes()).hexdigest()
def cache_dir(root,source):return pathlib.Path(root)/'stem-cache'/hashlib.sha256((VERSION+digest(source)).encode()).hexdigest()
def _valid(directory,meta):
    import soundfile as sf
    try:
        info=[]
        for name in NAMES:
            file=directory/name
            if file.is_symlink() or not file.is_file() or digest(file)!=meta['hashes'][name]:return False
            audio=sf.info(file);info.append((audio.frames,audio.samplerate,audio.channels))
        return info[0]==info[1] and info[0][0]>0 and info[0][1]==44100
    except (OSError,ValueError,KeyError,RuntimeError):return False
def restore(root,source,destination):
    root=pathlib.Path(root);source=pathlib.Path(source);directory=cache_dir(root,source);src=None
    try:
        meta=json.loads((directory/'meta.json').read_text(encoding='utf-8'))
        if meta['version']==VERSION and meta['sourceSha256']==digest(source) and _valid(directory,meta):src=directory
    except (OSError,ValueError,KeyError):pass
    if src is None:
        # Existing verified jobs are an immediate cold-start source for the cache.
        source_hash=digest(source)
        for file in (root/'performance-cache').glob('*.json'):
            try:
                record=json.loads(file.read_text(encoding='utf-8'));job=pathlib.Path(record.get('job','')).resolve()
                if record.get('normalizedSha256')!=source_hash or not record.get('quality',{}).get('passed'):continue
                if job.parent!=(root/'jobs').resolve() or not re.fullmatch('[0-9a-f-]{36}',job.name) or job.is_symlink():continue
                stems=job/'separated/htdemucs/source'
                if digest(job/'source.wav')!=source_hash or digest(stems/'vocals.wav')!=record.get('vocalSha256'):continue
                meta={'hashes':{n:digest(stems/n) for n in NAMES}}
                if not _valid(stems,meta):continue
                store(root,source,stems);src=directory;break
            except (OSError,ValueError,KeyError,RuntimeError):continue
    if src is None:return False
    destination=pathlib.Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for name in NAMES:shutil.copyfile(src/name,destination/name)
    os.utime(src/'meta.json',None);return True
def store(root,source,stems):
    directory=cache_dir(root,source);directory.parent.mkdir(parents=True,exist_ok=True)
    temp=pathlib.Path(tempfile.mkdtemp(prefix='.pending-',dir=directory.parent))
    try:
        for name in NAMES:shutil.copyfile(pathlib.Path(stems)/name,temp/name)
        meta={'version':VERSION,'sourceSha256':digest(source),'hashes':{n:digest(temp/n) for n in NAMES}}
        if not _valid(temp,meta):raise ValueError('Invalid separated audio')
        (temp/'meta.json').write_text(json.dumps(meta),encoding='utf-8')
        directory.mkdir(exist_ok=True)
        for name in (*NAMES,'meta.json'):os.replace(temp/name,directory/name)
    finally:
        # temp is generated directly inside this cache; never remove caller paths.
        if temp.resolve().parent!=directory.parent.resolve() or temp.is_symlink():raise RuntimeError('Unsafe cache temporary path')
        shutil.rmtree(temp)
