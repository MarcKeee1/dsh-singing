"""Cut a verified full performance on its unedited source timeline, with no VC run."""
import hashlib,pathlib,subprocess,time,uuid
import numpy as np
import soundfile as sf
from selection import select_range,mode_of
from instrumental_gaps import edit_mix,VERSION


def cut_full(master,record,request,output,*,root,ffmpeg):
    started=time.monotonic();job=pathlib.Path(record['job']);source=job/'source.wav'
    total=sf.info(master).duration
    start,stop,selection=select_range(request,source,total,record['sourceInfo'],root=root,ffmpeg=ffmpeg)
    with sf.SoundFile(master) as handle:
        rate=handle.samplerate;handle.seek(round(start*rate));mixed=handle.read(round((stop-start)*rate),always_2d=True)
    with sf.SoundFile(job/'separated/htdemucs/source/vocals.wav') as handle:
        if handle.samplerate!=rate:raise ValueError('缓存轨道采样率不一致')
        handle.seek(round(start*rate));vocals=handle.read(len(mixed),always_2d=True)
    hop=max(1,rate//100);frames=len(vocals)//hop
    rms=np.sqrt(np.mean(vocals[:frames*hop].reshape(frames,hop,-1)**2,axis=(1,2)))
    voiced=int((rms>.001).sum())
    if voiced<max(200,int((stop-start)*100*.15)):raise ValueError('所选缓存片段可辨认的歌声太少，请换一个起点')
    mixed,plan=edit_mix(mixed,vocals,rate)
    directory=root/'slice-cache';directory.mkdir(exist_ok=True)
    temporary=directory/(str(uuid.uuid4())+'.wav')
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        sf.write(temporary,mixed,rate,subtype='PCM_24')
        done=subprocess.run([ffmpeg,'-v','error','-y','-i',str(temporary),'-c:a','libmp3lame','-b:a','128k',str(output)],
            capture_output=True,timeout=max(60,(stop-start)*2),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if done.returncode:raise ValueError('缓存歌声剪切编码失败')
    finally:temporary.unlink(missing_ok=True)
    return {**record,'path':str(output),'seconds':round(len(mixed)/rate,2),
        'sourceInfo':{**record['sourceInfo'],'sourceStartSeconds':start,'seconds':stop-start,'selection':selection,
                      'sourceComplete':mode_of(request)=='full','positionRequest':selection.get('positionRequest')},
        'quality':{**record['quality'],'scope':'verified_full_master','sliceAudibleFrames':voiced},
        'gapEditVersion':VERSION,'gapEdits':plan,'audioSha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'cacheHit':True,'cacheMode':'full_performance_slice','elapsedSeconds':round(time.monotonic()-started,2),'sentToQQ':False}
