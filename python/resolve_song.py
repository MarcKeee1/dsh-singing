"""Find a public original performance and cut a short repeated chorus passage."""
import hashlib
import html
import json
import math
import pathlib
import re
import subprocess
import urllib.parse
import urllib.request
import urllib.error
import unicodedata
from difflib import SequenceMatcher
from song_identity import name_key, canonical_artist, artist_key, prefer_bilibili
from bili_source import resolve_bili, BiliSourceError, public_audio_url
from song_position import PositionError, position_spec, bounds, locate_position

from runtime import ROOT, FFMPEG
from source_choice import SourceChoiceRequired
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'}
KNOWN = {'493735012': {'bvid': 'BV1bb4y147UC', 'chorusHint': '如果云层'},
         '64625': {'mvId': 58923, 'mvOffset': 1.70}}
MAX_SECONDS = float("inf")


def normalized(text):
    return name_key(text)


def get_json(url, form=None):
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    headers = dict(HEADERS)
    if urllib.parse.urlparse(url).hostname == 'music.163.com':
        headers['Referer'] = 'https://music.163.com/'
    request = urllib.request.Request(url, data=data, headers=headers)
    from bili_session import open_request
    opener=open_request(ROOT,request) if urllib.parse.urlparse(url).hostname=='api.bilibili.com' else urllib.request.urlopen(request,timeout=20)
    with opener as response:
        return json.load(response)


def timed_lines(lyric):
    result = []
    for line in lyric.splitlines():
        stamps = re.findall(r'\[(\d+):(\d+(?:\.\d+)?)\]', line)
        content = re.sub(r'\[[^]]*\]', '', line).strip()
        if not content or re.search(r'作词|作曲|编曲|制作人|混音|母带|出品|录音|发行|监制', content):
            continue
        for minute, second in stamps:
            result.append((int(minute) * 60 + float(second), content))
    return sorted(set(result))


def choose_chorus(lines, song_seconds, hint=''):
    if hint:
        # LRC providers often split a single phrase into several timestamped lines.
        hits = [time for i, (time, content) in enumerate(lines)
                if any(0 <= normalized(''.join(x[1] for x in lines[i:i+n])).find(normalized(hint))
                       < len(normalized(content)) for n in [1, 2, 3])]
        if hits:
            return hits[0], 'lyric_hint'
    candidates = []
    for i, (start, text) in enumerate(lines):
        if start < max(20, song_seconds * .16) or start > song_seconds * .65:
            continue
        for j in range(i + 1, len(lines)):
            if lines[j][0] - start < 25:
                continue
            length = 0
            while i + length < j and j + length < len(lines) and normalized(lines[i + length][1]) == normalized(lines[j + length][1]):
                length += 1
            if length >= 3:
                span = lines[min(i + length, len(lines) - 1)][0] - start
                candidates.append((min(span, 35) + min(length, 8), -start, start))
    if not candidates:
        raise ValueError('没有可靠定位副歌；请给出副歌开头几个字或原曲链接，未随便截取主歌')
    return max(candidates)[2], 'repeated_lyric_section'


def artist_matches(name, requested):
    return artist_key(name) == artist_key(requested)


def chorus_end(lines, start, song_seconds):
    """Follow the repeated section, allowing small lyric changes on its last line."""
    first = min(range(len(lines)), key=lambda i: abs(lines[i][0] - start))
    candidates = []
    for repeat in range(first + 1, len(lines)):
        if lines[repeat][0] - start < 25:
            continue
        length, exact = 0, 0
        while first + length < repeat and repeat + length < len(lines):
            a = normalized(lines[first + length][1])
            b = normalized(lines[repeat + length][1])
            similarity = SequenceMatcher(None, a, b).ratio()
            if not a or similarity < .65:
                break
            exact += a == b
            length += 1
        if length >= 3 and exact >= 2:
            end = lines[first + length][0] if first + length < len(lines) else song_seconds
            if 5 <= end - start <= MAX_SECONDS:
                candidates.append((length, exact, end))
    if not candidates:
        raise ValueError('已找到副歌起点，但暂时无法可靠确定整段结束；可指定较短秒数或提供音频片段')
    return max(candidates)[2]


def select_segment(lines, song_seconds, duration=None, hint=''):
    try:
        start, method = choose_chorus(lines, song_seconds, hint)
    except ValueError:
        start = next((stamp for stamp, text in lines if stamp >= 1 and len(normalized(text)) >= 3), min(30, song_seconds * .15))
        method = 'vocal_excerpt'
    if duration is None and method != 'vocal_excerpt':
        try:
            return start, chorus_end(lines, start, song_seconds), method + '+complete_section'
        except ValueError:
            pass
    length = min(MAX_SECONDS, max(5, float(duration))) if duration is not None else 45
    endings = [stamp for stamp, _ in lines if start + min(12, length) <= stamp <= start + length]
    stop = max(endings) if endings else min(song_seconds, start + length)
    return start, stop, method + '+vocal_excerpt'


def title_matches(name, requested):
    # A studio edition is fine; a cover/live/remix/short clip is not an original.
    name = re.sub(r'[（(](?:唱片版|专辑版|Album Version|Remaster(?:ed)?)[）)]\s*$', '', str(name), flags=re.I)
    return normalized(name) == normalized(requested)


def valid_cache(record):
    try:
        source=pathlib.Path(record['source']).resolve(strict=True)
        return (source.parent==(ROOT/'song-cache').resolve() and record.get('sourceComplete') is True
            and math.isfinite(float(record['seconds'])) and float(record['seconds'])>=5
            and hashlib.sha256(source.read_bytes()).hexdigest()==record['sha256'])
    except (OSError,KeyError,ValueError,TypeError):return False


def download_full(info,song,artist):
    import soundfile as sf
    parsed=urllib.parse.urlparse(info['url'])
    if parsed.scheme not in {'http','https'} or parsed.username or parsed.password or parsed.port not in (None,80,443) or not any((parsed.hostname or '').endswith(d) for d in info['domains']):raise ValueError('平台音轨地址不符合公开媒体域名要求')
    url=urllib.parse.urlunparse(parsed._replace(scheme='https'))
    total=float(info['total'])
    if not math.isfinite(total) or total<5:raise ValueError('平台音轨时长无效')
    key=hashlib.sha256((info['songId']+':full-v1').encode()).hexdigest()[:24]
    directory=ROOT/'song-cache';directory.mkdir(exist_ok=True)
    path=directory/(key+'.wav');partial=path.with_suffix('.part.wav')
    done=subprocess.run([FFMPEG,'-v','error','-y','-user_agent','Mozilla/5.0','-referer',info['referer'],
        '-i',url,'-vn','-ar','44100','-ac','2',str(partial)],capture_output=True,
        timeout=max(120,total*2),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if done.returncode or not partial.is_file():
        partial.unlink(missing_ok=True);raise ValueError('平台已提供播放地址，但音轨读取或解码失败')
    actual=sf.info(partial).duration
    if abs(actual-total)>max(2,total*.01):
        partial.unlink(missing_ok=True);raise ValueError('实际音轨不完整，未把试听片段当作整首')
    partial.replace(path)
    return {**{k:v for k,v in info.items() if k not in {'url','referer','domains'}},'song':song or info.get('song',''),'artist':artist or info.get('artist',''),
        'source':str(path),'sourceStartSeconds':0,'seconds':actual,'sourceTotalSeconds':actual,'sourceComplete':True,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def resolve_netease(song,artist,source_url=''):
    if source_url:
        parsed=urllib.parse.urlparse(source_url);ident=urllib.parse.parse_qs(parsed.query).get('id',[''])[0]
        if parsed.hostname!='music.163.com' or parsed.path!='/song' or not ident.isdigit():raise ValueError('请提供网易云单曲链接')
        tracks=get_json('https://music.163.com/api/song/detail/?'+urllib.parse.urlencode({'ids':'['+ident+']','id':ident})).get('songs',[])
    else:
        search=get_json('https://music.163.com/api/search/get/web',{'s':artist+' '+song,'type':1,'limit':30,'offset':0})
        tracks=(search.get('result') or {}).get('songs') or []
    for track in tracks:
        artists=track.get('artists') or track.get('ar') or []
        if not source_url and (not title_matches(track.get('name',''),song) or (artist and not any(artist_matches(a.get('name',''),artist) for a in artists))):continue
        if track.get('originCoverType')==2:continue
        total=float(track.get('duration') or track.get('dt') or 0)/1000
        if total<5:continue
        play=get_json('https://music.163.com/api/song/enhance/player/url',{'ids':json.dumps([track['id']]),'br':128000})
        row=(play.get('data') or [{}])[0]
        if row.get('code')!=200 or not row.get('url') or row.get('freeTrialInfo') or row.get('fee') in (1,4):continue
        lyrics=get_json('https://music.163.com/api/song/lyric?'+urllib.parse.urlencode({'id':track['id'],'lv':1,'kv':1,'tv':-1}))
        return download_full({'url':row['url'],'total':total,'songId':'netease:'+str(track['id']),
            'sourcePage':'https://music.163.com/song?id='+str(track['id']),'sourceProvider':'netease',
            'referer':'https://music.163.com/','domains':['.music.126.net','.vod.126.net'],
            'lyricLines':timed_lines((lyrics.get('lrc') or {}).get('lyric',''))},song or track.get('name',''),artist or ' / '.join(a.get('name','') for a in artists))
    raise ValueError('网易云未找到版本相符、可公开完整播放的音轨')


PROVIDER_ORDER=('bilibili','netease','qqmusic')

def resolve_uncached(song,artist,source_url='',providers=None):
    from public_providers import resolve_qqmusic
    artist=canonical_artist(artist)
    providers=providers or {
        'bilibili':lambda:resolve_bili(song,artist,source_url=source_url,root=ROOT,fetch=get_json,ffmpeg=FFMPEG,full=True),
        'netease':lambda:resolve_netease(song,artist,source_url),
        'qqmusic':lambda:download_full(resolve_qqmusic(song,artist,source_url),song,artist)}
    order=PROVIDER_ORDER
    if source_url:
        p=urllib.parse.urlparse(source_url)
        names={'www.bilibili.com':'bilibili','bilibili.com':'bilibili','b23.tv':'bilibili','music.163.com':'netease','y.qq.com':'qqmusic'}
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.hostname not in names:raise ValueError('原曲链接需来自支持的平台 HTTPS 单曲页')
        order=(names[p.hostname],)
    attempts=[];alternatives=[]
    for provider in order:
        try:
            record=providers[provider]()
            return {**record,'sourceAttempts':attempts+[{'provider':provider,'status':'selected'}]}
        except (OSError,ValueError,KeyError,TypeError) as error:
            if isinstance(error,SourceChoiceRequired):alternatives.extend(error.options)
            status='access_denied' if isinstance(error,urllib.error.HTTPError) and error.code in {401,403,412,429} else 'unavailable'
            attempts.append({'provider':provider,'status':status,'reason':str(error)[:180]})
            if source_url:raise ValueError(provider+' 指定音源失败：'+str(error)) from error
    if alternatives:raise SourceChoiceRequired(alternatives)
    raise ValueError('音源平台均没有可用结果：'+'；'.join(x['provider']+': '+x['reason'] for x in attempts))


def resolve_public(song,artist='',source_url=''):
    artist=canonical_artist(artist)
    from source_reuse import find_verified_full
    known=find_verified_full(ROOT,song,artist,source_url)
    if known:return known
    key=hashlib.sha256(json.dumps([normalized(song),artist,source_url,'full-sources-v1',PROVIDER_ORDER],ensure_ascii=False).encode()).hexdigest()
    directory=ROOT/'lookup-cache';directory.mkdir(exist_ok=True)
    path=directory/(key+'.json')
    if path.is_file():
        try:
            record=json.loads(path.read_text(encoding='utf-8'))
            if valid_cache(record):return record
        except (ValueError,OSError):pass
    record=resolve_uncached(song,artist,source_url)
    import soundfile as sf
    actual=sf.info(record['source']).duration
    if abs(actual-record['seconds'])>max(2,record['seconds']*.01):raise ValueError('音源不完整，未当作整首使用')
    record['seconds']=record['sourceTotalSeconds']=actual
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record
