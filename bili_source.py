"""Independent public Bilibili source lookup; no NetEase catalog prerequisite."""
import hashlib
import json
import math
import pathlib
import re
import subprocess
import urllib.error
import urllib.parse
from song_identity import plain, name_key, canonical_artist
from song_position import position_spec, bounds, locate_position

class BiliSourceError(ValueError):
    pass

# Public video pages whose metadata was checked locally. They still undergo
# normal page, performer, version, playback and audio checks on use.
PREFERRED = {('周杰伦', '搁浅'): 'BV1M4411P7gM'}
BAD_VERSION = re.compile(r'翻唱|伴奏|纯音乐|钢琴|吉他|演奏|教学|现场|演唱会|串烧|混剪|合集|加速|慢速|变速|降调|升调|解说|挑战|模仿|原唱[:：]|(?:AI|ai)[ _-]*(?:翻|唱|换|cover)|\b(?:cover|live|remix|reaction)\b|DJ', re.I)

def parse_bvid(url):
    parsed = urllib.parse.urlparse(url)
    match = re.fullmatch(r'/video/(BV[0-9A-Za-z]{10})/?', parsed.path)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.bilibili.com', 'bilibili.com'} or parsed.username or parsed.password or not match:
        raise BiliSourceError('请使用完整的 https://www.bilibili.com/video/BV... 链接')
    if urllib.parse.parse_qs(parsed.query).get('p', ['1']) != ['1']:
        raise BiliSourceError('暂不从合集分P自动选歌，请提供单曲视频链接')
    return match[1]

def title_score(title, song, artist):
    title, song, artist = plain(title), plain(song), canonical_artist(artist)
    if not song or not artist or BAD_VERSION.search(title):
        return 0
    quoted = re.findall(r'《([^》]+)》', title)
    if quoted and not any(name_key(x) == name_key(song) for x in quoted):
        return 0
    aliases = [artist, 'Jay Chou'] if artist == '周杰伦' else [artist]
    if not any(name_key(a) in name_key(title) for a in aliases):
        return 0
    matches = list(re.finditer(re.escape(song), title, re.I))
    if not matches:
        return 0
    # Avoid treating e.g. 晴天娃娃 as 晴天. Common version labels can follow
    # without punctuation; quoted exact titles already establish the boundary.
    if not quoted and not any(not title[m.end():m.end()+1] or not re.match(r'[\w]', title[m.end():m.end()+1])
        or re.match(r'(?:MV|官方|原版|原曲|录音室|歌词|完整版|高音质|无损|Official)', title[m.end():], re.I) for m in matches):
        return 0
    if re.search(r'官方|official', title, re.I):return 3
    if re.search(r'(?<![a-z])MV(?![a-z])|music\s*video|音乐录影带', title, re.I):return 2
    if re.search(r'原版|原曲|录音室|歌词|高音质|无损|Hi.?Res|lyrics', title, re.I):return 1
    return 0

def duration_seconds(value):
    if isinstance(value, (int, float)):return float(value)
    parts = str(value).split(':')
    try:return sum(float(part)*60**index for index,part in enumerate(reversed(parts)))
    except ValueError:return 0

def public_json(fetch, url):
    try:
        result = fetch(url)
    except urllib.error.HTTPError as error:
        if error.code in {401,403,412,429}:
            raise BiliSourceError('B站当前限制了这次访问，请稍后再试；没有改换歌手或绕过限制') from error
        raise BiliSourceError('B站音源暂时无法访问，请稍后再试') from error
    except (OSError, TimeoutError) as error:
        raise BiliSourceError('B站查找暂时超时，请稍后再试') from error
    if result.get('code') in {-352,-412,-403,-401,429}:
        raise BiliSourceError('B站当前限制了这次访问，请稍后再试')
    return result

def candidates(song, artist, source_url, fetch):
    if source_url:return [parse_bvid(source_url)]
    preferred = PREFERRED.get((canonical_artist(artist), plain(song)))
    if preferred:return [preferred]
    url='https://api.bilibili.com/x/web-interface/search/type?'+urllib.parse.urlencode({'search_type':'video','keyword':f'{canonical_artist(artist)} {plain(song)} MV','page':1})
    result=public_json(fetch,url)
    if result.get('code') != 0:raise BiliSourceError('B站搜索暂时不可用，请稍后再试')
    ranked=[]
    for video in (result.get('data') or {}).get('result') or []:
        score=title_score(video.get('title',''),song,artist)
        bvid=video.get('bvid','')
        seconds=duration_seconds(video.get('duration',0))
        if score and 90 <= seconds <= 600 and re.fullmatch(r'BV[0-9A-Za-z]{10}',bvid):
            ranked.append((score,int(video.get('play',0) or 0),bvid))
    return list(dict.fromkeys(item[2] for item in sorted(ranked,reverse=True)))[:3]

def resolve_bili(song, artist, duration=None, hint='', source_url='', *, root, fetch, ffmpeg, run=subprocess.run, start_seconds=None, lyric_occurrence=1):
    spec=position_spec(start_seconds,hint,lyric_occurrence)
    song,artist=plain(song),canonical_artist(artist)
    if not song or not artist:
        raise BiliSourceError('独立查找B站原曲需要歌名和歌手，请补充歌手；没有改用同名翻唱')
    requested=float(duration) if duration is not None else 45.0
    if not math.isfinite(requested) or not 5 <= requested <= 90:raise BiliSourceError('片段时长需在5到90秒之间')
    choices=candidates(song,artist,source_url,fetch)
    if not choices:raise BiliSourceError(f'B站没有找到歌名、歌手和版本都符合的《{song}》音源')
    cache=root/'song-cache';cache.mkdir(exist_ok=True)
    for bvid in choices:
        view=public_json(fetch,'https://api.bilibili.com/x/web-interface/view?'+urllib.parse.urlencode({'bvid':bvid}))
        if view.get('code') != 0:continue
        info=view.get('data') or {}
        total=duration_seconds(info.get('duration',0))
        if not title_score(info.get('title',''),song,artist) or not 90 <= total <= 600 or len(info.get('pages') or [])>1:continue
        if (info.get('rights') or {}).get('pay'):continue
        cid=info.get('cid')
        if not isinstance(cid,int) or cid<=0:continue
        url=None;alignment=None
        if spec:
            url=public_audio_url(fetch,bvid,cid)
            if not url:continue
            start,alignment=locate_position(spec,url,'https://www.bilibili.com/',f'bili:{bvid}:{cid}',total,root=root,ffmpeg=ffmpeg,run=run)
            start,stop=bounds(start,total,duration)
            seconds=stop-start
        else:
            start=min(60.0,total*.25)
            seconds=min(requested,total-start-.2)
        digest=hashlib.sha256(json.dumps([bvid,cid,start,seconds,spec if spec else 'bili-independent-v1']).encode()).hexdigest()[:24]
        audio,record_path=cache/(digest+'.wav'),cache/(digest+'.json')
        if audio.is_file() and record_path.is_file():
            try:
                old=json.loads(record_path.read_text(encoding='utf-8'))
                if (old.get('artist')==artist and old.get('song')==song and old.get('seconds')==seconds
                    and hashlib.sha256(audio.read_bytes()).hexdigest()==old.get('sha256')):return old
            except (OSError,ValueError):pass
        if not url:url=public_audio_url(fetch,bvid,cid)
        if not url:continue
        partial=audio.with_suffix('.part.wav')
        completed=run([ffmpeg,'-v','error','-y','-user_agent','Mozilla/5.0','-referer','https://www.bilibili.com/',
            '-ss',str(start),'-i',url,'-t',str(seconds),'-vn','-ar','44100','-ac','2',str(partial)],capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode or not partial.is_file():
            raise BiliSourceError('已找到B站原曲，但音轨读取失败；本次没有改用其他歌手')
        partial.replace(audio)
        record={'source':str(audio),'song':song,'artist':artist,'songId':f'bili:{bvid}:{cid}',
            'sourcePage':f'https://www.bilibili.com/video/{bvid}','sourceAuthor':(info.get('owner') or {}).get('name',''),
            'sourceTitle':info.get('title',''),'sourceProvider':'bilibili','sourceMatch':'title_artist_version_metadata',
            'chorusStartSeconds':start,'sourceStartSeconds':start,'seconds':seconds,'timelineAligned':False,
            'chorusMethod':'bilibili_independent_vocal_excerpt','sha256':hashlib.sha256(audio.read_bytes()).hexdigest()}
        if spec:record.update({'positionRequest':spec,'alignment':alignment,'timelineAligned':True,'sourceTimeline':'selected_source','chorusMethod':'requested_'+spec['mode']})
        record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        return record
    raise BiliSourceError(f'找到了B站候选，但没有可正常读取、版本相符的{artist}《{song}》音轨')


def public_audio_url(fetch,bvid,cid):
    play=public_json(fetch,'https://api.bilibili.com/x/player/playurl?'+urllib.parse.urlencode({'bvid':bvid,'cid':cid,'fnval':16,'qn':64}))
    if play.get('code')!=0:return None
    data=play.get('data') or {}
    if data.get('is_preview'):return None
    streams=sorted((data.get('dash') or {}).get('audio') or [],key=lambda row:row.get('bandwidth',0),reverse=True)
    url=(streams[0].get('baseUrl') or streams[0].get('base_url')) if streams else None
    if not url:return None
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.username or parsed.password or not any((parsed.hostname or '').endswith(suffix) for suffix in ['.bilivideo.com','.bilivideo.cn']):
        raise BiliSourceError('B站返回的音轨地址不在允许的公开媒体域名内')
    return url
