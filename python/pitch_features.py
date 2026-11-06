"""Content-addressed pitch features; one CPU model per worker, no pickle data."""
import hashlib,json,os,pathlib,tempfile,time
import numpy as np

VERSION=1
_model=None
_model_fingerprint=None
stats={'hits':0,'misses':0,'modelLoads':0}

def model_fingerprint():
    global _model_fingerprint
    if _model_fingerprint is None:
        from runtime import MODELS
        _model_fingerprint=hashlib.sha256((MODELS/'lj1995--VoiceConversionWebUI/rmvpe.pt').read_bytes()).hexdigest()
    return _model_fingerprint

def load_model():
    global _model
    if _model is None:
        import sys,torch
        from runtime import MODELS,VENDOR
        sys.path.insert(0,str(VENDOR))
        from modules.rmvpe import RMVPE
        torch.set_num_threads(4)
        _model=RMVPE(str(MODELS/'lj1995--VoiceConversionWebUI/rmvpe.pt'),is_half=False,device='cpu')
        stats['modelLoads']+=1
    return _model

def extract(path,cache_dir=None,*,model_id=None,infer=None):
    """Same 20 s chunking as QA; cache keyed by audio and model, verified on read."""
    from runtime import ROOT
    path=pathlib.Path(path);cache=pathlib.Path(cache_dir or ROOT/'pitch-cache')
    key=hashlib.sha256((hashlib.sha256(path.read_bytes()).hexdigest()+str(VERSION)+(model_id or model_fingerprint())).encode()).hexdigest()
    file=cache/(key+'.npz')
    if file.is_file() and not file.is_symlink():
        try:
            with np.load(file,allow_pickle=False) as data:
                f0=data['f0'];samples=int(data['samples']);stored=str(data['digest'])
                if samples<1 or f0.ndim!=1 or f0.dtype!=np.float32 or len(f0)!=samples//160 or not np.isfinite(f0).all():raise ValueError('shape')
                if hashlib.sha256(f0.tobytes()).hexdigest()!=stored:raise ValueError('hash')
                os.utime(file,None);stats['hits']+=1;return f0,samples
        except (OSError,ValueError,KeyError,EOFError):pass
    import librosa
    wave,_=librosa.load(path,sr=16000);parts=[]
    infer=infer or (lambda chunk:load_model().infer_from_audio(chunk,thred=.05))
    for start in range(0,len(wave),20*16000):
        chunk=wave[start:start+20*16000]
        if len(chunk)<160:continue
        parts.append(np.asarray(infer(chunk),dtype=np.float32)[:len(chunk)//160])
    f0=np.concatenate(parts) if parts else np.empty(0,dtype=np.float32)
    if len(f0)!=len(wave)//160 or not np.isfinite(f0).all():raise ValueError('Invalid extracted pitch')
    cache.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=cache,suffix='.tmp',delete=False) as stream:
        temp=pathlib.Path(stream.name)
        np.savez_compressed(stream,f0=f0,samples=len(wave),digest=hashlib.sha256(f0.tobytes()).hexdigest())
    os.replace(temp,file);stats['misses']+=1
    return f0,len(wave)

def register_sample(f0,samples):
    span=20*16000
    starts=sorted(set([0,max(0,samples//2-span//2),max(0,samples-span)])) if samples>span else [0]
    return np.concatenate([f0[start//160:(start+span)//160] for start in starts])
