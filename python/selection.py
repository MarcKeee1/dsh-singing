"""Selections use the original recording timeline, never an edited playback clock."""
import math
from song_position import request_position, bounds, locate_position, transcript, PositionError
from song_identity import name_key


def mode_of(request):
    mode=request.get('mode') or ('from' if request_position(request) else 'excerpt')
    if mode not in {'full','chorus','from','excerpt','opening','opening_to_chorus','long'}:raise PositionError('无效唱歌模式')
    position=request_position(request)
    if mode=='full' and (position or request.get('duration') is not None):raise PositionError('整首模式不同时指定起点或片段时长')
    if mode in {'chorus','opening','opening_to_chorus'} and position:raise PositionError('结构选段与指定起点请选择一种')
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
        if not value or not 0<=a<=b<=total+1:continue
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
            if (length>=18 and b-a>=10 and any(end>start for start,end in stamps[j:j+length])
                    and any(end>start for start,end in stamps[i:i+length])
                    and all(stamps[k+1][0]-stamps[k][1]<6 for k in range(j,j+length-1))):
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
    if mode=='long':
        # A longer casual excerpt must not require transcribing the entire song.
        starts=sorted(float(stamp) for stamp,text in (metadata.get('lyricLines') or [])
                      if name_key(text) and 0<=float(stamp)<total)
        start=starts[0] if starts else min(60,total*.25,max(0,total-5))
        target=min(total,start+(float(duration) if duration is not None else 90))
        # Prefer a nearby lyric boundary, without expanding into another chorus.
        endings=[x for x in starts[1:]+[total] if max(start+5,target-10)<=x<=target]
        stop=max(endings) if endings and duration is None else target
        start,stop=bounds(start,total,stop-start)
        return start,stop,{'method':'long_section','selectionConfidence':'lyric_timeline' if starts else 'excerpt',
                           'softTargetSeconds':90,'fullTranscriptionRequired':False}
    if mode in {'chorus','opening','opening_to_chorus'}:
        if not metadata.get('lyricLines'):
            from lyric_alignment import enrich_lyrics
            metadata=enrich_lyrics(source,total,metadata,root=root)
        lines=metadata.get('lyricLines') or []
        words=[]
        if lines:
            from resolve_song import choose_chorus,chorus_end
            starts=sorted(float(stamp) for stamp,text in lines if name_key(text) and 0<=float(stamp)<total)
            if not starts:raise PositionError('没有可用的起唱时间')
            first=starts[0];endings=starts[1:]+[total]
            def chorus():
                a,_=choose_chorus(lines,total);return a,chorus_end(lines,a,total)
        else:
            words=transcript(str(source),'',metadata['songId'],total,root=root,ffmpeg=ffmpeg)
            words=sorted((w for w in words if name_key(w.get('text','')) and 0<=float(w.get('start',0))<=float(w.get('end',0))<=total+1),key=lambda w:float(w['start']))
            if not words:raise PositionError('没有可用的起唱时间')
            first=max(0,float(words[0]['start'])-.12)
            endings=[min(total,float(w['end'])+.15) for i,w in enumerate(words) if i==len(words)-1 or float(words[i+1]['start'])-float(w['end'])>=.35 or any(c in w['text'] for c in '。！？.!?')]
            if not endings:endings=[total]
            def chorus():return repeated_chorus(words,total)
        if mode in {'chorus','opening_to_chorus'}:
            a,b=chorus();start=a if mode=='chorus' else first;stop=b
        elif mode=='opening':
            start=first
            try:a,b=chorus();stop=a if a-first>=5 else next((x for x in endings if x>=first+25),total)
            except ValueError:stop=next((x for x in endings if x>=first+30),total)
        if duration is not None:stop=min(stop,start+float(duration))
        start,stop=bounds(start,total,stop-start)
        method={'chorus':'repeated_section','opening':'opening_section','opening_to_chorus':'opening_through_first_chorus'}[mode]
        return start,stop,{'method':method,'selectionConfidence':'repeated_lyrics' if mode in {'chorus','opening_to_chorus'} else 'lyric_timeline','softTargetSeconds':None,
                           **({'lyricsAlignment':metadata['lyricsAlignment']} if metadata.get('lyricsAlignment') else {})}
    start=min(60,total*.25,max(0,total-5))
    start,stop=bounds(start,total,duration if duration is not None else 45)
    return start,stop,{'method':'vocal_excerpt'}
