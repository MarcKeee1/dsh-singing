"""Bounded, formant-preserving repair of measured whole-octave VC errors."""
import pathlib,subprocess,json
import numpy as np

def octave_masks(expected,actual):
    n=min(len(expected),len(actual));s=np.asarray(expected[:n]);c=np.asarray(actual[:n]);pair=(s>65)&(c>65)
    error=1200*np.log2(np.maximum(c,1)/np.maximum(s,1))
    return {'up':pair&(error>-1500)&(error<-900),'down':pair&(error>900)&(error<1500)}

def repair(source,converted,folder,base_shift,profile=None):
    import soundfile as sf
    from scipy.ndimage import gaussian_filter1d,maximum_filter1d
    from runtime import FFMPEG
    from pitch_features import extract
    from phrase_register import apply
    from pitch_check import check
    source=pathlib.Path(source);current=pathlib.Path(converted);folder=pathlib.Path(folder);folder.mkdir(parents=True,exist_ok=True)
    source_f0,_=extract(source);expected=apply(source_f0,profile,base_shift);report={'ok':False,'attempts':[]}
    for iteration in range(2):
        actual,_=extract(current);masks=octave_masks(expected,actual);wave,rate=sf.read(current,always_2d=True);mixed=wave.copy();used=0
        for direction,factor in [('up',2),('down',.5)]:
            mask=masks[direction]
            if not mask.any():continue
            shifted=folder/f'{iteration}-{direction}.wav'
            subprocess.run([FFMPEG,'-v','error','-y','-i',str(current),'-af',f'apad=pad_dur=1,rubberband=pitch={factor}:formant=preserved:transients=smooth,atrim=duration={len(wave)/rate}','-c:a','pcm_f32le',str(shifted)],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            fixed,sr=sf.read(shifted,always_2d=True)
            if sr!=rate or abs(len(fixed)-len(wave))>2:raise ValueError('Pitch repair changed timing')
            if len(fixed)<len(wave):fixed=np.pad(fixed,((0,len(wave)-len(fixed)),(0,0)))
            envelope=gaussian_filter1d(maximum_filter1d(mask.astype(float),size=3),sigma=.7)
            weight=np.interp(np.arange(len(wave))/rate,np.arange(len(mask))/100,envelope,left=0,right=0)[:,None]
            mixed+=weight*(fixed[:len(wave)]-wave);used+=int(mask.sum())
        if not used:break
        candidate=folder/f'pass-{iteration}.wav';sf.write(candidate,mixed,rate,subtype='FLOAT');quality=check(source,candidate,base_shift,profile)
        report['attempts'].append({'correctedFrames':used,'quality':quality});current=candidate
        if quality['passed']:report.update(ok=True,path=str(candidate));break
    if not report['attempts']:report['quality']=check(source,current,base_shift,profile)
    report.setdefault('path',str(current));(folder/'report.json').write_text(json.dumps(report,indent=2),'utf-8')
    return report
