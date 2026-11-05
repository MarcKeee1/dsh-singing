"""Independent public Bilibili source lookup; no NetEase catalog prerequisite."""
import hashlib
import json
import math
import pathlib
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from song_identity import plain, name_key, canonical_artist
from song_position import position_spec, bounds, locate_position
from source_choice import SourceChoiceRequired

class BiliSourceError(ValueError):
    pass

# Public video pages whose metadata was checked locally. They still undergo
# normal page, performer, version, playback and audio checks on use.
BAD_VERSION = re.compile(r'翻唱|伴奏|纯音乐|钢琴|吉他|演奏|教学|现场|演唱会|串烧|混剪|合集|加速|慢速|变速|降调|升调|解说|对白|剧情版|采访|观众|挑战|模仿|原唱[:：]|(?:AI|ai)[ _-]*(?:翻|唱|换|cover)|\b(?:cover|live|remix|reaction)\b|DJ', re.I)

def parse_bvid(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == 'https' and parsed.hostname == 'b23.tv':
        return parse_bvid(resolve_short_url(url))
    match = re.fullmatch(r'/video/(BV[0-9A-Za-z]{10})/?', parsed.path)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.bilibili.com', 'bilibili.com'} or parsed.username or parsed.password or not match:
        raise BiliSourceError('请使用完整的 https://www.bilibili.com/video/BV... 链接')
    if urllib.parse.parse_qs(parsed.query).get('p', ['1']) != ['1']:
        raise BiliSourceError('暂不从合集分P自动选歌，请提供单曲视频链接')
    return match[1]

class _ResolvedVideo(Exception):
    pass

class _BiliShortRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        self.hops=0
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.hops+=1
        parsed=urllib.parse.urlparse(newurl)
        if self.hops>3 or parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443):
            raise BiliSourceError('B站短链接跳转异常，请提供完整 BV 视频链接')
        if parsed.hostname in {'www.bilibili.com','bilibili.com'}:
            bvid=parse_bvid(newurl)
            raise _ResolvedVideo('https://www.bilibili.com/video/'+bvid)
        if parsed.hostname!='b23.tv':
            raise BiliSourceError('B站短链接没有指向 B站视频，请提供完整 BV 视频链接')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def resolve_short_url(url):
    parsed=urllib.parse.urlparse(url)
    if (parsed.scheme!='https' or parsed.hostname!='b23.tv' or parsed.username or parsed.password
        or parsed.port not in (None,443) or not re.fullmatch(r'/[A-Za-z0-9]{4,30}/?',parsed.path)):
        raise BiliSourceError('B站短链接格式无效，请提供完整 BV 视频链接')
    try:
        opener=urllib.request.build_opener(_BiliShortRedirects())
        request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        with opener.open(request,timeout=15):
            raise BiliSourceError('B站短链接没有返回视频跳转，请提供完整 BV 视频链接')
    except _ResolvedVideo as target:
        return str(target)
    except urllib.error.HTTPError as error:
        if error.code in {401,403,412,429}:
            raise BiliSourceError('B站当前限制了短链接访问，请稍后再试') from error
        raise BiliSourceError('B站短链接暂时无法访问，请提供完整 BV 视频链接') from error
    except (OSError,TimeoutError) as error:
        raise BiliSourceError('B站短链接访问超时，请稍后再试或提供完整 BV 视频链接') from error

def explicit_title_matches(title,song,artist):
    """A user-selected version need not advertise itself as official/MV.

    Keep both requested song and performer/version in the metadata. This is
    deliberately separate from the strict automatic original-song ranking.
    """
    title,song,artist=plain(title),plain(song),canonical_artist(artist)
    if not song or not artist:return False
    aliases=[artist,'Jay Chou'] if artist=='周杰伦' else [artist]
    if not any(name_key(a) in name_key(title) for a in aliases):return False
    def contains_song(value):
        for match in re.finditer(re.escape(song),value,re.I):
            before=value[match.start()-1:match.start()] if match.start() else ''
            after=value[match.end():]
            if before and re.match(r'\w',before):continue
            if not after or not re.match(r'\w',after) or re.match(r'(?:MV|官方|原版|原曲|录音室|歌词|完整版|高音质|无损|Official|翻唱|现场|伴奏|改编|混音|cover|live|remix)',after,re.I):return True
        return False
    quoted=re.findall(r'[《「『]([^》」』]+)[》」』]',title)
    return any(contains_song(value) for value in quoted) if quoted else contains_song(title)

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
    if re.search(r'官方音频|Official\s*Audio|Audio\s*Only|Lyric(?:s)?\s*(?:Video)?|歌词版|纯享|录音室|专辑音源',title,re.I):return 5
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
    url='https://api.bilibili.com/x/web-interface/search/type?'+urllib.parse.urlencode({'search_type':'video','keyword':f'{canonical_artist(artist)} {plain(song)}','page':1})
    result=public_json(fetch,url)
    if result.get('code') != 0:raise BiliSourceError('B站搜索暂时不可用，请稍后再试')
    ranked=[]
    for video in (result.get('data') or {}).get('result') or []:
        score=title_score(video.get('title',''),song,artist) if artist else automatic_score(video,song,artist)
        bvid=video.get('bvid','')
        seconds=duration_seconds(video.get('duration',0))
        if math.isfinite(seconds) and seconds >= 5 and re.fullmatch(r'BV[0-9A-Za-z]{10}',bvid):
            ranked.append((score,int(video.get('play',0) or 0),bvid))
    return list(dict.fromkeys(item[2] for item in sorted(ranked,reverse=True)))[:3]

def automatic_score(info,song,artist):
    title=plain(info.get('title',''));description=plain(info.get('desc',''))
    if BAD_VERSION.search(title):return 0
    if artist:
        score=title_score(title,song,artist)
        if score:return score
        aliases=[canonical_artist(artist)]
        if canonical_artist(artist)=='周杰伦':aliases.append('Jay Chou')
        # Credits can be in the description rather than the upload title.
        if name_key(song) in name_key(title+' '+description) and any(name_key(a) in name_key(description) for a in aliases):return 1
        return 0
    if name_key(song) not in name_key(title+' '+description):return 0
    return 2 if re.search(r'原唱|官方|录音室|Official\s*Audio|专辑音源',title+' '+description,re.I) else 0

def resolve_bili(song, artist, duration=None, hint='', source_url='', *, root, fetch, ffmpeg, run=subprocess.run, start_seconds=None, lyric_occurrence=1, full=False):
    spec=position_spec(start_seconds,hint,lyric_occurrence)
    song,artist=plain(song),canonical_artist(artist)
    if not source_url and not song:
        raise BiliSourceError('请提供歌名或具体视频链接；歌手可以省略')
    requested=float(duration) if duration is not None else 45.0
    if not math.isfinite(requested) or requested < 5:raise BiliSourceError('片段时长至少5秒')
    choices=candidates(song,artist,source_url,fetch)
    if not choices:raise BiliSourceError(f'B站没有找到歌名、歌手和版本都符合的《{song}》音源')
    cache=root/'song-cache';cache.mkdir(exist_ok=True)
    alternatives=[]
    for bvid in choices:
        view=public_json(fetch,'https://api.bilibili.com/x/web-interface/view?'+urllib.parse.urlencode({'bvid':bvid}))
        if view.get('code') != 0:
            if source_url:raise BiliSourceError('指定的 B站视频资料暂时无法读取；尚未检查音轨，请不要归因为禁止下载')
            continue
        info=view.get('data') or {}
        total=duration_seconds(info.get('duration',0))
        if source_url:
            # A user-picked video is the version selection. Generic upload
            # titles and missing performer credits must not veto that choice.
            song=song or plain(info.get('title','')) or '指定视频音轨'
            artist=artist or '视频指定版本'
            if not math.isfinite(total) or total<5 or len(info.get('pages') or [])>1:
                raise BiliSourceError('指定视频需为至少5秒的单曲音源；尚未请求音轨，不是下载权限问题')
        elif not math.isfinite(total) or total<5 or len(info.get('pages') or [])>1:continue
        if any((info.get('rights') or {}).get(key) for key in ('pay','ugc_pay','arc_pay')):
            if source_url:raise BiliSourceError('指定视频标记为付费内容，当前公开取音频方式不支持；没有绕过播放权限')
            continue
        if not source_url and not automatic_score(info,song,artist):
            alternatives.append({'title':plain(info.get('title',''))[:160],'source_url':'https://www.bilibili.com/video/'+bvid,'version':'其他版本或歌手未确认'})
            continue
        cid=info.get('cid')
        if not isinstance(cid,int) or cid<=0:continue
        url=None;alignment=None
        if full:
            start,stop,seconds=0,total,total
        elif spec:
            url=public_audio_url(fetch,bvid,cid)
            if not url:continue
            start,alignment=locate_position(spec,url,'https://www.bilibili.com/',f'bili:{bvid}:{cid}',total,root=root,ffmpeg=ffmpeg,run=run)
            start,stop=bounds(start,total,duration)
            seconds=stop-start
        else:
            start=min(60.0,total*.25,max(0,total-5))
            start,stop=bounds(start,total,requested)
            seconds=stop-start
        digest=hashlib.sha256(json.dumps([bvid,cid,start,seconds,spec if spec else 'bili-independent-v1',*(['explicit-version-v1'] if source_url else [])]).encode()).hexdigest()[:24]
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
        try:
            completed=run([ffmpeg,'-v','error','-y','-user_agent','Mozilla/5.0','-referer','https://www.bilibili.com/',
                '-ss',str(start),'-i',url,'-t',str(seconds),'-vn','-ar','44100','-ac','2',str(partial)],capture_output=True,timeout=max(90,seconds*2),creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        except subprocess.TimeoutExpired as error:
            partial.unlink(missing_ok=True)
            raise BiliSourceError('B站已返回播放地址，但读取音频超时；不能据此判断视频禁止下载') from error
        if completed.returncode or not partial.is_file():
            partial.unlink(missing_ok=True)
            raise BiliSourceError('B站已返回播放地址，但音频读取或解码失败；不是没有音频流，本次没有改用其他歌手')
        partial.replace(audio)
        record={'source':str(audio),'song':song,'artist':artist or '视频未标注歌手','songId':f'bili:{bvid}:{cid}',
            'sourcePage':f'https://www.bilibili.com/video/{bvid}','sourceAuthor':(info.get('owner') or {}).get('name',''),
            'sourceTitle':info.get('title',''),'sourceProvider':'bilibili','sourceMatch':'user_selected_video' if source_url else 'title_artist_version_metadata',
            'chorusStartSeconds':start,'sourceStartSeconds':start,'seconds':seconds,'timelineAligned':False,
            'chorusMethod':'bilibili_independent_vocal_excerpt','sha256':hashlib.sha256(audio.read_bytes()).hexdigest()}
        record.update(sourceTotalSeconds=total,sourceComplete=full)
        if spec:record.update({'positionRequest':spec,'alignment':alignment,'timelineAligned':True,'sourceTimeline':'selected_source','chorusMethod':'requested_'+spec['mode']})
        record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        return record
    if alternatives:raise SourceChoiceRequired(alternatives)
    raise BiliSourceError(f'找到了B站候选，但没有可正常读取、版本相符的{artist}《{song}》音轨')


def public_audio_url(fetch,bvid,cid):
    play=public_json(fetch,'https://api.bilibili.com/x/player/playurl?'+urllib.parse.urlencode({'bvid':bvid,'cid':cid,'fnval':16,'qn':64}))
    if play.get('code')!=0:
        raise BiliSourceError('B站播放接口未成功返回播放资料；无法判断是否有音轨，请稍后再试')
    data=play.get('data') or {}
    if data.get('is_preview') or data.get('is_drm') or data.get('drm_tech_type'):
        raise BiliSourceError('B站仅返回试看或受保护播放资料，当前方式不读取这类内容')
    dash=data.get('dash') or {}
    streams=sorted(dash.get('audio') or [],key=lambda row:row.get('bandwidth',0),reverse=True)
    if not streams:
        streams=list((dash.get('dolby') or {}).get('audio') or [])
        flac=(dash.get('flac') or {}).get('audio')
        if isinstance(flac,dict):streams.append(flac)
    url=next((row.get('baseUrl') or row.get('base_url') or row.get('url') for row in streams if row.get('baseUrl') or row.get('base_url') or row.get('url')),None)
    if not url:
        # Some playable responses contain a combined video/audio file rather
        # than a separate audio track. ffmpeg can extract its audio directly.
        combined=data.get('durl') or []
        if len(combined)==1:url=combined[0].get('url')
        elif len(combined)>1:
            raise BiliSourceError('B站返回了多段合并音视频，当前还不支持拼接这类音源；不是禁止下载')
    if not url:
        raise BiliSourceError('B站这次播放资料中没有可用音轨或合并音视频地址；不能据此断言作者关闭了下载')
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.username or parsed.password or not any((parsed.hostname or '').endswith(suffix) for suffix in ['.bilivideo.com','.bilivideo.cn']):
        raise BiliSourceError('B站返回的音轨地址不在允许的公开媒体域名内')
    return url
