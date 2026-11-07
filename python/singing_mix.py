"""Foreground singing without changing voice, pitch, tempo, or the source stems."""
import numpy as np
from scipy.signal import butter, sosfiltfilt

VERSION=4
CLARITY_VERSION=1
from runtime import CONFIG
MUSIC_GAIN=CONFIG.get('musicGain',.55)
VOICE_GAIN=CONFIG.get('voiceGain',1.25)

def _bell(rate,hz,db,q):
    # Half the gain per pass: forward/backward filtering retains sample timing.
    a=10**(db/80);w=2*np.pi*hz/rate;alpha=np.sin(w)/(2*q);c=np.cos(w)
    b=np.array([1+alpha*a,-2*c,1-alpha*a]);den=np.array([1+alpha/a,-2*c,1-alpha/a])
    return np.r_[b/den[0],den/den[0]]

def _shelf(rate,hz,db):
    a=10**(db/80);w=2*np.pi*hz/rate;c=np.cos(w);alpha=np.sin(w)/np.sqrt(2);v=2*np.sqrt(a)*alpha
    b=a*np.array([(a+1)+(a-1)*c+v,-2*((a-1)+(a+1)*c),(a+1)+(a-1)*c-v])
    den=np.array([(a+1)-(a-1)*c+v,2*((a-1)-(a+1)*c),(a+1)-(a-1)*c-v])
    return np.r_[b/den[0],den/den[0]]

def clarify_vocal(voice,rate,*,harmony=False):
    wave=np.asarray(voice,dtype=np.float64)
    if rate<8000 or not np.isfinite(wave).all():raise ValueError('Invalid vocal samples')
    if len(wave)<32:return wave.copy()
    sos=[*butter(1,55,fs=rate,btype='highpass',output='sos'),_bell(rate,280,-1.0 if harmony else -1.6,.85)]
    if not harmony:
        sos.append(_bell(rate,min(2900,rate*.32),1.8,.8))
        sos.append(_shelf(rate,min(6500,rate*.4),.7))
    return sosfiltfilt(np.asarray(sos),wave,axis=0)

def clarity_settings():
    return {'version':CLARITY_VERSION,'highpassHz':55,'lowMidHz':280,'lowMidDb':-1.6,
            'presenceHz':2900,'presenceDb':1.8,'airHz':6500,'airDb':.7,
            'harmonyPresenceBoostDb':0,'zeroPhase':True,'pitchShiftSemitones':0}

def mix_tracks(source_vocals,instrumental,converted,rate):
    raw=np.asarray(source_vocals);music=np.asarray(instrumental);voice=np.asarray(converted)
    if raw.ndim==1:raw=raw[:,None]
    if music.ndim==1:music=music[:,None]
    if voice.ndim==1:voice=voice[:,None]
    if abs(len(raw)-len(music))/rate>.1 or abs(len(voice)-len(music))/rate>.1:
        raise ValueError('歌声与伴奏长度不一致，未混音')
    match=float(np.clip(np.sqrt(np.mean(raw**2))/max(1e-8,np.sqrt(np.mean(voice**2))),.5,2))
    clear=clarify_vocal(voice,rate)
    aligned=np.zeros((len(music),1));aligned[:min(len(aligned),len(clear)),0]=clear[:len(aligned),0]
    mixed=MUSIC_GAIN*music+VOICE_GAIN*match*aligned
    peak=float(np.max(np.abs(mixed)))
    if not np.isfinite(mixed).all() or peak<.001:raise ValueError('混音音频无效')
    scale=min(1,.89/peak);mixed*=scale
    fade=min(round(rate*.025),len(mixed)//2)
    mixed[:fade]*=np.linspace(0,1,fade)[:,None];mixed[-fade:]*=np.linspace(1,0,fade)[:,None]
    return mixed,{'version':VERSION,'clarity':clarity_settings(),'voiceLayers':'single_lead','harmonyRelativeGain':0,'musicGain':MUSIC_GAIN,'voiceGain':VOICE_GAIN,'sourceVoiceMatchGain':match,'relativeVocalBoostDb':round(20*np.log10(VOICE_GAIN/MUSIC_GAIN),2),'peakScale':scale,'peak':round(float(np.max(np.abs(mixed))),4)}
