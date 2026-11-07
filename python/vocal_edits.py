"""Explicit phrase corrections, bound to the exact source audio, never a title."""
import pathlib,hashlib,json,re
import numpy as np

def rule(root,source_hash):
    if not re.fullmatch('[0-9a-f]{64}',str(source_hash)):return None
    path=pathlib.Path(root)/'edited-performance-cache/vocal-edits'/(source_hash+'.json')
    if not path.is_file() or path.is_symlink():return None
    if path.stat().st_size>65536:raise ValueError('Vocal correction is too large')
    raw=path.read_bytes();value=json.loads(raw)
    if value.get('sourceSha256')!=source_hash or value.get('version')!=1:raise ValueError('Vocal correction source mismatch')
    intervals=value.get('muteIntervals')
    if not isinstance(intervals,list) or len(intervals)>100:raise ValueError('Invalid phrase corrections')
    previous=0
    for pair in intervals:
        if not isinstance(pair,list) or len(pair)!=2 or not all(isinstance(x,(int,float)) and np.isfinite(x) for x in pair) or not 0<=pair[0]<pair[1]:raise ValueError('Invalid phrase interval')
        if pair[0]<previous:raise ValueError('Overlapping phrase intervals')
        previous=pair[1]
    return {**value,'signature':hashlib.sha256(raw).hexdigest()}

def signature(root,record):
    value=rule(root,record.get('normalizedSha256'))
    return value['signature'] if value else ''

def apply(voice,rate,job):
    job=pathlib.Path(job).resolve();root=job.parent.parent
    if job.parent!=root/'jobs' or not (job/'source.wav').is_file():return voice,None
    source_hash=hashlib.sha256((job/'source.wav').read_bytes()).hexdigest();value=rule(root,source_hash)
    if not value:return voice,None
    envelope=np.ones(len(voice));fade=max(1,round(rate*.055))
    for a,b in value['muteIntervals']:
        start=round(a*rate);stop=round(b*rate)
        if stop>len(voice)+1:raise ValueError('Phrase correction is outside the source timeline')
        start=max(0,start);stop=min(len(voice),stop);n=min(fade,(stop-start)//2)
        envelope[start:stop]=0
        if n:
            down=(1+np.cos(np.linspace(0,np.pi,n)))/2
            envelope[start:start+n]=np.minimum(envelope[start:start+n]+down,1)
            envelope[stop-n:stop]=np.minimum(envelope[stop-n:stop]+down[::-1],1)
    return np.asarray(voice)*envelope.reshape((-1,)+(1,)*(np.asarray(voice).ndim-1)),{'signature':value['signature'],'sourceSha256':source_hash,'muteIntervals':value['muteIntervals'],'fadeSeconds':.055}
