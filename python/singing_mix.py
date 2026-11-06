"""Foreground singing without changing voice, pitch, tempo, or the source stems."""
import numpy as np

VERSION=2
from runtime import CONFIG
MUSIC_GAIN=CONFIG.get('musicGain',.55)
VOICE_GAIN=CONFIG.get('voiceGain',1.25)

def mix_tracks(source_vocals,instrumental,converted,rate):
    raw=np.asarray(source_vocals);music=np.asarray(instrumental);voice=np.asarray(converted)
    if raw.ndim==1:raw=raw[:,None]
    if music.ndim==1:music=music[:,None]
    if voice.ndim==1:voice=voice[:,None]
    if abs(len(raw)-len(music))/rate>.1 or abs(len(voice)-len(music))/rate>.1:
        raise ValueError('歌声与伴奏长度不一致，未混音')
    match=float(np.clip(np.sqrt(np.mean(raw**2))/max(1e-8,np.sqrt(np.mean(voice**2))),.5,2))
    aligned=np.zeros((len(music),1));aligned[:min(len(aligned),len(voice)),0]=voice[:len(aligned),0]
    mixed=MUSIC_GAIN*music+VOICE_GAIN*match*aligned
    peak=float(np.max(np.abs(mixed)))
    if not np.isfinite(mixed).all() or peak<.001:raise ValueError('混音音频无效')
    scale=min(1,.89/peak);mixed*=scale
    fade=min(round(rate*.025),len(mixed)//2)
    mixed[:fade]*=np.linspace(0,1,fade)[:,None];mixed[-fade:]*=np.linspace(1,0,fade)[:,None]
    return mixed,{'version':VERSION,'musicGain':MUSIC_GAIN,'voiceGain':VOICE_GAIN,'sourceVoiceMatchGain':match,'relativeVocalBoostDb':round(20*np.log10(VOICE_GAIN/MUSIC_GAIN),2),'peakScale':scale,'peak':round(float(np.max(np.abs(mixed))),4)}
