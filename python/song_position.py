"""Validate excerpt requests and locate a supplied phrase on its actual audio."""
import hashlib
import json
import math
import os
import pathlib
import subprocess
import sys
from song_identity import name_key

class PositionError(ValueError):
    pass

def position_spec(start=None,hint='',occurrence=1):
    hint=name_key(hint or '')
    if start is not None and hint:
        raise PositionError('歌词起句和秒数起点请选一种，不能同时指定')
    if isinstance(occurrence,bool) or not isinstance(occurrence,(int,float)) or not math.isfinite(occurrence) or int(occurrence)!=occurrence or not 1<=occurrence<=10:
        raise PositionError('歌词出现次数需为1到10的整数')
    if hint:
        if not 4<=len(hint)<=120:raise PositionError('请给至少四个字的起唱歌词，最多120字，便于准确定位')
        return {'version':1,'mode':'lyric','hint':hint,'occurrence':int(occurrence)}
    if occurrence!=1:raise PositionError('指定第几次出现时，需要同时提供起唱歌词')
    if start is not None:
        if isinstance(start,bool):raise PositionError('起点秒数无效')
        try:start=float(start)
        except (TypeError,ValueError):raise PositionError('起点秒数无效') from None
        if not math.isfinite(start) or start<0:raise PositionError('起点秒数需为非负有限数字')
        return {'version':1,'mode':'seconds','startSeconds':round(start,3)}
    return None

def request_position(request):
    # Legacy requests wrote zero even when no start was supplied. New requests
    # preserve omission as null, and explicitly mark the semantics version.
    start=request.get('start')
    if request.get('positionVersion')!=1 and start in (None,0):start=None
    return position_spec(start,request.get('chorus_hint',''),request.get('lyric_occurrence',1))

def bounds(start,total,duration=None):
    length=total-start if duration is None else float(duration)
    if not math.isfinite(length) or length<5:raise PositionError('片段时长至少5秒')
    if not math.isfinite(total) or not 0<=start<total or total-start<5:
        raise PositionError('指定起点已超出音源，或剩余不足5秒；请换一个更早的起点')
    return start,min(total,start+length)

def match_words(words,hint,occurrence=1):
    """Exact normalized phrase matching, never use the requested phrase as an ASR prompt."""
    target=name_key(hint)
    if len(target)<4:raise PositionError('请给至少四个字的起唱歌词')
    text,positions='',[]
    for word in words:
        try:
            start,end=float(word['start']),float(word['end'])
            value=name_key(word['text'])
            if not value or not math.isfinite(start+end) or start<0 or not start<end:continue
            for char in value:positions.append((start,end))
            text+=value
        except (KeyError,ValueError,TypeError):continue
    hits=[];offset=0
    while True:
        found=text.find(target,offset)
        if found<0:break
        stamps=positions[found:found+len(target)];start,end=stamps[0][0],stamps[-1][1]
        # Do not join a phrase across an instrumental break or overlapping,
        # malformed timestamp spans. Repeated choruses stay distinct.
        valid=(0<end-start<=max(18,len(target)*1.4)
               and all(0<=b[0]-a[0]<=5 and b[0]-a[1]<=3 for a,b in zip(stamps,stamps[1:])))
        if valid and (not hits or start-hits[-1]['matchedStartSeconds']>2):
            hits.append({'matchedStartSeconds':round(start,3),'matchedEndSeconds':round(end,3),
                         'sourceStartSeconds':round(max(0,start-.12),3),'match':'exact_normalized_words'})
        offset=found+max(1,len(target))
    if len(hits)<occurrence:
        raise PositionError('没有在这版音轨中可靠找到指定歌词或对应次数；请换一句更完整的歌词，或直接指定秒数')
    return {**hits[occurrence-1],'occurrence':occurrence,'foundOccurrences':len(hits)}

def transcript(url,referer,identity,total,*,root,ffmpeg,run=subprocess.run):
    directory=root/'alignment-cache';directory.mkdir(exist_ok=True)
    # No signed playback URL or user phrase in the cache key; one timeline is
    # reusable for every requested phrase in the same source recording.
    identity_hash=hashlib.sha256(json.dumps([identity,'whisper-small-973afd-word-v1']).encode()).hexdigest()
    audio=directory/(identity_hash+'.wav');record_path=directory/(identity_hash+'.json')
    if record_path.is_file() and audio.is_file():
        try:
            record=json.loads(record_path.read_text(encoding='utf-8'))
            if record['audioSha256']==hashlib.sha256(audio.read_bytes()).hexdigest():
                return record['words']
        except (KeyError,ValueError,TypeError,OSError) as error:
            if isinstance(error,PositionError):raise
    if not math.isfinite(total) or total<5:raise PositionError('音源时长无效')
    partial=audio.with_suffix('.part.wav')
    options=['-user_agent','Mozilla/5.0','-referer',referer] if referer else []
    try:
        completed=run([ffmpeg,'-v','error','-y',*options,'-i',url,'-t',str(total),'-vn','-ar','16000','-ac','1',str(partial)],
                      capture_output=True,timeout=max(120,total*2),creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    except subprocess.TimeoutExpired:
        raise PositionError('读取歌词定位用的音轨超时；可以稍后重试') from None
    if completed.returncode or not partial.is_file():raise PositionError('已找到音源，但读取歌词定位用的音轨失败')
    partial.replace(audio)
    raw=directory/(identity_hash+'.words.json');log=directory/(identity_hash+'.worker.log')
    try:
        with log.open('a',encoding='utf-8') as output:
            completed=run([sys.executable,str(pathlib.Path(__file__).with_name('transcribe_song.py')),
                           '--audio',str(audio),'--output',str(raw)],stdout=output,stderr=output,
                          timeout=max(420,total*10),creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
                          env={**os.environ,'PYTHONIOENCODING':'utf-8','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'})
        if completed.returncode or not raw.is_file():raise PositionError('本地歌词定位失败；可以改为指定秒数')
    except subprocess.TimeoutExpired:
        raise PositionError('这次歌词定位耗时过长；可以改为指定秒数') from None
    record=json.loads(raw.read_text(encoding='utf-8'))
    record.update({'audioSha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'identity':identity})
    temp=record_path.with_suffix('.tmp');temp.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8');temp.replace(record_path)
    return record['words']


def locate_lyric(url,referer,identity,total,hint,occurrence,*,root,ffmpeg,run=subprocess.run):
    return match_words(transcript(url,referer,identity,total,root=root,ffmpeg=ffmpeg,run=run),hint,occurrence)

def locate_position(spec,url,referer,identity,total,*,root,ffmpeg,run=subprocess.run):
    if spec['mode']=='seconds':return spec['startSeconds'],{'method':'requested_seconds'}
    match=locate_lyric(url,referer,identity,total,spec['hint'],spec['occurrence'],root=root,ffmpeg=ffmpeg,run=run)
    return match['sourceStartSeconds'],{**match,'method':'actual_audio_word_timestamps'}
