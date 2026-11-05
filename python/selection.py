"""Selections use the original recording timeline, never an edited playback clock."""
import math
from song_position import request_position, bounds, locate_position, transcript, PositionError
from song_identity import name_key


def mode_of(request):
    mode=request.get('mode') or ('from' if request_position(request) else 'excerpt')
    if mode not in {'full','chorus','from','excerpt'}:raise PositionError('无效唱歌模式')
    position=request_position(request)
    if mode=='full' and (position or request.get('duration') is not None):raise PositionError('整首模式不同时指定起点或片段时长')
    if mode=='chorus' and position:raise PositionError('只唱副歌与指定起点请选择一种')
    if mode=='from' and not position:raise PositionError('请给起点秒数或起唱歌词')
    duration=request.get('duration')
    if duration is not None and (isinstance(duration,bool) or not math.isfinite(float(duration)) or float(duration)<5):raise PositionError('时长至少5秒')
    return mode


def repeated_chorus(words,total):
    """Find a substantial repeated phrase run; fail rather than label any clip a chorus."""
    text='';stamps=[]
    for word in words:
        value=name_key(word.get('text',''))
        a,b=float(word.get('start',0)),float(word.get('end',0))
        if not value or not 0<=a<b<=total+1:continue
        text+=value;stamps.extend([(a,b)]*len(value))
    candidates=[]
    # Repeated 12+ character anchors separated by at least 20 seconds.
    anchors={}
    for i in range(max(0,len(text)-11)):
        anchor=text[i:i+12]
        for j in anchors.get(anchor,[]):
            if stamps[i][0]-stamps[j][0]<20 or stamps[j][0]<total*.12:continue
            length=12
            while j+length<i and i+length<len(text) and text[j+length]==text[i+length]:length+=1
            a,b=stamps[j][0],stamps[j+length-1][1]
            if length>=18 and b-a>=10 and all(stamps[k+1][0]-stamps[k][1]<6 for k in range(j,j+length-1)):
                candidates.append((length,b-a,-a,max(0,a-.12),min(total,b+.3)))
        anchors.setdefault(anchor,[]).append(i)
    if not candidates:raise PositionError('没有可靠确定副歌范围；可指定起唱歌词、秒数，或改唱整首')
    best=max(candidates)
    return best[-2],best[-1]


def select_range(request,source,total,metadata,*,root,ffmpeg):
    mode=mode_of(request);position=request_position(request);duration=request.get('duration')
    if not math.isfinite(total) or total<5:raise PositionError('音源不足5秒或时长无效')
    if mode=='full':return 0,total,{'method':'full','sourceComplete':True}
    if position:
        start,alignment=locate_position(position,str(source),'',metadata['songId'],total,root=root,ffmpeg=ffmpeg)
        start,stop=bounds(start,total,duration)
        return start,stop,{'method':'requested_'+position['mode'],'alignment':alignment,'positionRequest':position}
    if mode=='chorus':
        lines=metadata.get('lyricLines') or []
        if lines:
            from resolve_song import choose_chorus,chorus_end
            start,_=choose_chorus(lines,total);stop=chorus_end(lines,start,total)
        else:
            words=transcript(str(source),'',metadata['songId'],total,root=root,ffmpeg=ffmpeg)
            start,stop=repeated_chorus(words,total)
        if duration is not None:stop=min(stop,start+float(duration))
        return start,stop,{'method':'repeated_section','selectionConfidence':'repeated_lyrics'}
    start=min(60,total*.25,max(0,total-5))
    start,stop=bounds(start,total,duration if duration is not None else 45)
    return start,stop,{'method':'vocal_excerpt'}
