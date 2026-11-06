"""Conservatively shorten long quiet spans in the separated vocal stem."""
import hashlib
import json
import pathlib
import subprocess
import numpy as np
import soundfile as sf
from singing_mix import mix_tracks, VERSION as MIX_VERSION

VERSION=1

def plan_gaps(vocals,rate):
    wave=np.asarray(vocals)
    if wave.ndim==1:wave=wave[:,None]
    seconds=len(wave)/rate;hop=max(1,round(rate*.02))
    count=len(wave)//hop
    if not count:return {'version':VERSION,'inputSeconds':seconds,'cuts':[],'removedSeconds':0}
    # Work on channel power to avoid phase cancellation. The low threshold and
    # padding protect quiet syllables, breaths and sustained note decays.
    rms=np.sqrt(np.mean(wave[:count*hop].reshape(count,hop,-1)**2,axis=(1,2)))
    threshold=max(.00005,min(.0015,float(np.percentile(rms,95))*.025))
    active=rms>threshold
    pad=round(.3/.02)
    protected=np.convolve(active.astype(int),np.ones(2*pad+1,dtype=int),'same')>0
    changes=np.diff(np.r_[True,protected,True].astype(int))
    starts=np.where(changes==-1)[0]*hop/rate;ends=np.where(changes==1)[0]*hop/rate
    cuts=[]
    # Leave about 1.2s of instrumental breathing room; brief rests stay intact.
    for start,end in zip(starts,ends):
        if end-start>=6:
            left=start+.6;right=end-(.2 if end>=seconds-.05 else .6)
            if right-left>=4:cuts.append([round(left,3),round(right,3)])
    removed=sum(b-a for a,b in cuts)
    if seconds-removed-len(cuts)*.04<5:cuts=[];removed=0
    return {'version':VERSION,'inputSeconds':round(seconds,4),'cuts':cuts,'removedSeconds':round(removed,4),'threshold':threshold,'minimumGapSeconds':6,'crossfadeSeconds':.04}

def apply_plan(wave,rate,plan):
    if not plan['cuts']:return wave
    parts=[];cursor=0
    for start,end in plan['cuts']:
        a,b=round(start*rate),round(end*rate)
        parts.append(wave[cursor:a]);cursor=b
    parts.append(wave[cursor:]);out=parts[0].copy()
    for part in parts[1:]:
        fade=min(round(.04*rate),len(out),len(part))
        if fade:
            weights=np.linspace(0,1,fade)
            if out.ndim>1:weights=weights[:,None]
            overlap=out[-fade:]*(1-weights)+part[:fade]*weights
            out=np.concatenate([out[:-fade],overlap,part[fade:]],axis=0)
        else:out=np.concatenate([out,part],axis=0)
    return out

def edit_mix(mixed,vocals,rate):
    from runtime import CONFIG
    if not CONFIG.get('shortenGaps',True):return mixed,{'version':VERSION,'inputSeconds':len(mixed)/rate,'outputSeconds':len(mixed)/rate,'removedSeconds':0,'cuts':[],'disabled':True}
    plan=plan_gaps(vocals,rate);out=apply_plan(mixed,rate,plan)
    plan.update({'outputSeconds':round(len(out)/rate,4),'removedSeconds':round((len(mixed)-len(out))/rate,4)})
    return out,plan

def cached_edited(audio,record,root,ffmpeg):
    if record.get('gapEditVersion')==VERSION and record.get('mixVersion')==MIX_VERSION:return audio,record
    directory=root/'edited-performance-cache';directory.mkdir(exist_ok=True)
    key=hashlib.sha256((record['audioSha256']+':gaps-v1:mix-v2').encode()).hexdigest()
    meta=directory/(key+'.json');edited=directory/(key+'.mp3')
    if meta.is_file() and edited.is_file():
        try:
            info=json.loads(meta.read_text(encoding='utf-8'))
            if info.get('mixVersion')==MIX_VERSION and hashlib.sha256(edited.read_bytes()).hexdigest()==info['audioSha256']:
                return edited,{**record,**info}
        except (OSError,ValueError,KeyError,TypeError):pass
    job=pathlib.Path(record.get('job','')).resolve()
    if job.parent!=(root/'jobs').resolve():return audio,{**record,'mixingStatus':'old_stems_unavailable'}
    vocals=job/'separated/htdemucs/source/vocals.wav';music=job/'separated/htdemucs/source/no_vocals.wav';converted=list((job/'converted').glob('*.wav'))
    if not vocals.is_file() or not music.is_file() or len(converted)!=1:return audio,{**record,'mixingStatus':'old_stems_unavailable'}
    raw,rate=sf.read(vocals,always_2d=True);instrumental,music_rate=sf.read(music,always_2d=True);voice,voice_rate=sf.read(converted[0],always_2d=True)
    if rate!=music_rate or rate!=voice_rate:raise ValueError('缓存歌声采样率不一致')
    if record.get('harmonyProcessing',{}).get('version'):
        from harmony_vocal import mix_job
        mixed,settings,raw,rate=mix_job(job)
    else:
        mixed,settings=mix_tracks(raw,instrumental,voice,rate)
    mixed,plan=edit_mix(mixed,raw,rate)
    wav=directory/(key+'.tmp.wav');partial=directory/(key+'.part.mp3')
    sf.write(wav,mixed,rate,subtype='PCM_24')
    try:
        done=subprocess.run([ffmpeg,'-v','error','-y','-i',str(wav),'-c:a','libmp3lame','-b:a','128k','-metadata','comment=AI singing voice conversion; vocal-forward mix; long instrumental gaps shortened',str(partial)],capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        if done.returncode:raise ValueError('歌声混音编码失败，本次未发送')
        partial.replace(edited)
    finally:
        if wav.is_file():wav.unlink()
    info={'seconds':round(len(mixed)/rate,2),'gapEditVersion':VERSION,'gapEdits':plan,'mixVersion':MIX_VERSION,'mixSettings':settings,'audioSha256':hashlib.sha256(edited.read_bytes()).hexdigest()}
    tmp=meta.with_suffix('.tmp');tmp.write_text(json.dumps(info),encoding='utf-8');tmp.replace(meta)
    return edited,{**record,**info}
