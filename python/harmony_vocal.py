"""Convert backing vocals independently, retaining their original overlap timing."""
import pathlib,json
import numpy as np,soundfile as sf
from singing_mix import mix_tracks,MUSIC_GAIN,VOICE_GAIN,VERSION as MIX_VERSION
VERSION=1
from runtime import CONFIG
HARMONY_GAIN=CONFIG.get('harmonyGain',.8)

def prepare(raw_path,lead_path,folder):
    from pitch_features import extract
    folder=pathlib.Path(folder);folder.mkdir(parents=True,exist_ok=True)
    raw,sr=sf.read(raw_path,always_2d=True);lead,rate=sf.read(lead_path,always_2d=True)
    if sr!=rate or raw.shape!=lead.shape:raise ValueError('Vocal stem alignment mismatch')
    residual=raw-lead
    ratio=float(np.sqrt(np.mean(residual**2))/max(1e-9,np.sqrt(np.mean(raw**2))))
    meta={'version':VERSION,'active':False,'rmsRatio':ratio,'relativeGain':HARMONY_GAIN,'sourceOriginalVocalsMixed':False}
    path=folder/'harmony.wav'
    if ratio>=.10 and np.sqrt(np.mean(residual**2))>=.001:
        sf.write(path,residual,sr,subtype='FLOAT')
        f0,_=extract(path);frames=int(((f0>65)&(f0<1100)).sum())
        meta.update(voicedFrames=frames,active=frames>=50)
    (folder/'harmony.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return path if meta['active'] else None,meta

def mix(raw,music,voice,rate,harmony_source=None,harmony_voice=None):
    if harmony_source is None or harmony_voice is None:return mix_tracks(raw,music,voice,rate)
    raw,music,voice,source,back=[np.asarray(a) for a in (raw,music,voice,harmony_source,harmony_voice)]
    if any(a.ndim!=2 or not np.isfinite(a).all() for a in (raw,music,voice,source,back)):
        raise ValueError('Invalid vocal track')
    if any(abs(len(a)-len(music))/rate>.1 for a in (raw,voice,source,back)):
        raise ValueError('Vocal tracks have different timing')
    main_gain=float(np.clip(np.sqrt(np.mean(raw**2))/max(1e-9,np.sqrt(np.mean(voice**2))),.5,2))
    backing_gain=float(np.clip(np.sqrt(np.mean(source**2))/max(1e-9,np.sqrt(np.mean(back**2))),.1,2))
    combined=np.zeros((len(music),1))
    combined[:min(len(music),len(voice)),0]+=main_gain*voice[:len(music),0]
    combined[:min(len(music),len(back)),0]+=HARMONY_GAIN*backing_gain*back[:len(music),0]
    mixed=MUSIC_GAIN*music+VOICE_GAIN*combined
    peak=float(np.max(np.abs(mixed)))
    if peak<.001:raise ValueError('Empty vocal mix')
    scale=min(1,.89/peak);mixed*=scale
    fade=min(round(rate*.025),len(mixed)//2)
    mixed[:fade]*=np.linspace(0,1,fade)[:,None];mixed[-fade:]*=np.linspace(1,0,fade)[:,None]
    return mixed,{'version':MIX_VERSION,'musicGain':MUSIC_GAIN,'voiceGain':VOICE_GAIN,'sourceVoiceMatchGain':main_gain,
                  'harmonyMatchGain':backing_gain,'harmonyRelativeGain':HARMONY_GAIN,'harmonyVersion':VERSION,
                  'relativeVocalBoostDb':round(20*np.log10(VOICE_GAIN/MUSIC_GAIN),2),'peakScale':scale,'peak':float(np.max(np.abs(mixed)))}

def mix_job(job):
    job=pathlib.Path(job);stems=job/'separated/htdemucs/source'
    raw,rate=sf.read(job/'lead/lead.wav',always_2d=True)
    voice,voice_rate=sf.read(next((job/'converted').glob('*.wav')),always_2d=True)
    music,music_rate=sf.read(stems/'no_vocals.wav',always_2d=True)
    if voice_rate!=rate or music_rate!=rate:raise ValueError('Vocal sample rates differ')
    meta=json.loads((job/'lead/harmony.json').read_text(encoding='utf-8'))
    source=back=None;gap_reference=raw
    if meta['active']:
        source,sr=sf.read(job/'lead/harmony.wav',always_2d=True)
        back,br=sf.read(next((job/'harmony-converted').glob('*.wav')),always_2d=True)
        if sr!=rate or br!=rate:raise ValueError('Harmony sample rates differ')
        gap_reference,_=sf.read(stems/'vocals.wav',always_2d=True)
    mixed,settings=mix(raw,music,voice,rate,source,back)
    return mixed,settings,gap_reference,rate
