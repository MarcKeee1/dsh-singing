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
from bili_source import resolve_bili, BiliSourceError
from song_position import PositionError, position_spec, bounds, locate_position

from runtime_config import ROOT, FFMPEG
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'}
KNOWN = {'493735012': {'bvid': 'BV1bb4y147UC', 'chorusHint': '如果云层'},
         '64625': {'mvId': 58923, 'mvOffset': 1.70}}
MAX_SECONDS = 90


def normalized(text):
    return name_key(text)


def get_json(url, form=None):
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    headers = dict(HEADERS)
    if urllib.parse.urlparse(url).hostname == 'music.163.com':
        headers['Referer'] = 'https://music.163.com/'
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
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
        source = pathlib.Path(record['source']).resolve(strict=True)
        return (source.parent == (ROOT / 'song-cache').resolve()
                and 4 <= float(record['seconds']) <= MAX_SECONDS
                and hashlib.sha256(source.read_bytes()).hexdigest() == record['sha256'])
    except (OSError, KeyError, ValueError, TypeError):
        return False


def extract_excerpt(url, start, stop, metadata, referer, exact=False):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ['https', 'http'] or parsed.username or parsed.password or not any(
            (parsed.hostname or '').endswith(domain) for domain in ['.music.126.net', '.vod.126.net']):
        raise ValueError('音轨来源不符合公开媒体域名要求')
    # Public provider URLs may advertise HTTP; use the same CDN over TLS.
    url = urllib.parse.urlunparse(parsed._replace(scheme='https'))
    key = hashlib.sha256(json.dumps([metadata['songId'], metadata['sourcePage'], start, stop, ['position-v1',metadata.get('positionRequest')] if exact else 'v2']).encode()).hexdigest()[:24]
    cache = ROOT / 'song-cache'
    cache.mkdir(exist_ok=True)
    destination, record_path = cache / (key + '.wav'), cache / (key + '.json')
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding='utf-8'))
        if valid_cache(record):
            return record
    seconds = min(MAX_SECONDS, stop - start + (0 if exact else .08))
    result = subprocess.run([FFMPEG, '-v', 'error', '-y', '-user_agent', HEADERS['User-Agent'],
        '-referer', referer, '-ss', str(start if exact else max(0, start - .08)), '-i', url, '-t', str(seconds),
        '-vn', '-ar', '44100', '-ac', '2', str(destination)], capture_output=True, timeout=90,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or not destination.is_file():
        raise ValueError('公开音轨截取失败')
    record = {**metadata, 'source': str(destination), 'seconds': seconds,
              'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def resolve_music_source(track, start, stop, method, known, requested_duration=None, position=None):
    metadata = {'song': track['name'], 'artist': ' '.join(a['name'] for a in track['artists']),
                'songId': str(track['id']), 'chorusStartSeconds': start, 'chorusMethod': method}
    # Only consume a normally playable full track. Never use VIP/trial endpoints.
    play = get_json('https://music.163.com/api/song/enhance/player/url', {'ids': json.dumps([track['id']]), 'br': 128000})
    data = (play.get('data') or [{}])[0]
    if data.get('code') == 200 and data.get('url') and not data.get('freeTrialInfo'):
        if position:
            return extract_positioned(data['url'],{**metadata,'sourcePage':'https://music.163.com/song?id='+str(track['id']),'sourceAuthor':metadata['artist']},'https://music.163.com/',track['duration']/1000,requested_duration,position)
        return extract_excerpt(data['url'], start, stop, {**metadata,
            'sourcePage': 'https://music.163.com/song?id=' + str(track['id']),
            'sourceAuthor': metadata['artist'], 'timelineOffsetSeconds': 0}, 'https://music.163.com/')
    mv_id = known.get('mvId') or track.get('mvid')
    if not mv_id:
        return None
    mv = get_json(f'https://music.163.com/api/mv/detail?id={mv_id}&type=mp4')
    info = mv.get('data') or {}
    artists = info.get('artists') or []
    # Some song records link to a cover MV by a different performer.
    if mv.get('code') != 200 or not title_matches(info.get('name', ''), track['name']) or not any(
            a.get('id') == b.get('id') and artist_matches(a.get('name',''), b.get('name',''))
            for a in artists for b in track['artists'] if a.get('id', 0) > 0):
        return None
    streams = info.get('brs') or {}
    if not streams:
        return None
    if position:
        return extract_positioned(streams[min(streams,key=int)],{**metadata,'sourcePage':f'https://music.163.com/mv?id={mv_id}','sourceAuthor':metadata['artist']},'https://music.163.com/',float(info.get('duration',0))/1000,requested_duration,position)
    if 'mvOffset' in known:
        offset = known['mvOffset']
        mv_start, mv_stop = start + offset, stop + offset
        metadata['timelineOffsetSeconds'] = offset
    else:
        # A requested song need not be a precisely located chorus. MV intro edits
        # make album LRC timestamps uncertain: select a continuous passage and
        # explicitly classify it as an excerpt, never as an aligned full chorus.
        mv_seconds = float(info.get('duration', 0)) / 1000
        length = min(stop - start, requested_duration if requested_duration is not None else 45, MAX_SECONDS, mv_seconds - .2)
        if length < 5:
            return None
        mv_start = min(max(0, start * mv_seconds / (track['duration'] / 1000)), mv_seconds - length - .1)
        mv_stop = mv_start + length
        metadata.update({'chorusMethod': 'public_mv_vocal_excerpt', 'timelineAligned': False})
    metadata['sourceStartSeconds'] = round(mv_start, 3)
    return extract_excerpt(streams[min(streams, key=int)], mv_start, mv_stop,
        {**metadata, 'sourcePage': f'https://music.163.com/mv?id={mv_id}',
         'sourceAuthor': metadata['artist']}, 'https://music.163.com/')


def resolve_public(song, artist='', duration=None, hint='', source_url='', start_seconds=None, lyric_occurrence=1):
    artist = canonical_artist(artist)
    duration = None if duration is None else float(duration)
    if duration is not None and (not math.isfinite(duration) or not 5<=duration<=MAX_SECONDS):
        raise PositionError('片段时长需在5到90秒之间')
    spec=position_spec(start_seconds,hint,lyric_occurrence)
    version = 7 if prefer_bilibili(artist) or source_url else 6
    parts=[normalized(song),artist,duration,hint,source_url,version] if not spec else [normalized(song),artist,duration,source_url,spec,8]
    key = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
    directory = ROOT / 'lookup-cache'
    directory.mkdir(exist_ok=True)
    path = directory / (key + '.json')
    if path.is_file():
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            if valid_cache(record):
                return record
        except (ValueError, OSError):
            pass
    record = resolve_uncached(song, artist, duration, hint, source_url, start_seconds, lyric_occurrence)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def resolve_uncached(song, artist='', duration=None, hint='', source_url='', start_seconds=None, lyric_occurrence=1):
    artist = canonical_artist(artist)
    position_spec(start_seconds,hint,lyric_occurrence)
    if prefer_bilibili(artist) or source_url:
        return resolve_bili(song, artist, duration, hint, source_url, root=ROOT, fetch=get_json, ffmpeg=FFMPEG, start_seconds=start_seconds, lyric_occurrence=lyric_occurrence)
    try:
        return resolve_netease(song, artist, duration, hint, start_seconds=start_seconds, lyric_occurrence=lyric_occurrence)
    except (BiliSourceError,PositionError):
        raise
    except (OSError, ValueError) as error:
        # Do not retry a blocked Bilibili request via another route. Otherwise
        # a missing/failed NetEase catalog is not a prerequisite for Bilibili.
        if isinstance(error, urllib.error.HTTPError) and urllib.parse.urlparse(error.url).hostname == 'api.bilibili.com':
            raise BiliSourceError('B站当前暂不可用，请稍后再试') from error
        if not artist:
            raise ValueError('网易云没有找到可用的明确版本，请补充歌手以独立查找B站；没有自动换成同名翻唱') from error
        return resolve_bili(song, artist, duration, hint, root=ROOT, fetch=get_json, ffmpeg=FFMPEG, start_seconds=start_seconds, lyric_occurrence=lyric_occurrence)


def resolve_netease(song, artist='', duration=None, hint='', source_url='', start_seconds=None, lyric_occurrence=1):
    spec=position_spec(start_seconds,hint,lyric_occurrence)
    query = (artist + ' ' + song).strip()
    search = get_json('https://music.163.com/api/search/get/web', {'s': query, 'type': 1, 'limit': 30, 'offset': 0})
    tracks = (search.get('result') or {}).get('songs') or []
    matches = [item for item in tracks if title_matches(item['name'], song) and item.get('duration', 0) >= 90000
               and any(a.get('id', 0) > 0 and (not artist or artist_matches(a['name'], artist)) for a in item.get('artists', []))]
    if not matches:
        raise ValueError('没有找到歌名与歌手一致的原曲；请补充准确歌名和歌手')
    track, lines = matches[0], []
    for candidate in ([] if spec else matches[:4]):
        lyrics = get_json('https://music.163.com/api/song/lyric?' + urllib.parse.urlencode({'id': candidate['id'], 'lv': 1, 'kv': 1, 'tv': -1}))
        candidate_lines = timed_lines((lyrics.get('lrc') or {}).get('lyric', ''))
        if len(candidate_lines) >= 8:
            track = candidate
            lines = candidate_lines
            break
    artist = ' '.join(a['name'] for a in track['artists'])
    song_id = str(track['id'])
    song_seconds = track['duration'] / 1000
    known = KNOWN.get(song_id, {})
    if spec:
        if known.get('bvid'):
            return resolve_bili(song,artist,duration,hint,'https://www.bilibili.com/video/'+known['bvid'],root=ROOT,fetch=get_json,ffmpeg=FFMPEG,start_seconds=start_seconds,lyric_occurrence=lyric_occurrence)
        record=resolve_music_source(track,0,45,'requested_position',known,duration,position=spec)
        if record:return record
        return resolve_bili(song,artist,duration,hint,root=ROOT,fetch=get_json,ffmpeg=FFMPEG,start_seconds=start_seconds,lyric_occurrence=lyric_occurrence)
    start, stop, method = select_segment(lines, song_seconds, duration, known.get('chorusHint', ''))
    if stop - start < 4:
        raise ValueError('副歌片段太短，未生成')
    if not source_url and not known.get('bvid'):
        try:
            record = resolve_music_source(track, start, stop, method, known, duration)
        except (OSError, ValueError):
            record = None
        if record:
            return record
        return resolve_bili(song, artist, duration, hint, root=ROOT, fetch=get_json, ffmpeg=FFMPEG)
    bvid = known.get('bvid')
    if source_url:
        url = urllib.parse.urlparse(source_url)
        match = re.fullmatch(r'/video/(BV[0-9A-Za-z]{10})/?', url.path)
        if url.scheme != 'https' or url.hostname not in ['www.bilibili.com', 'bilibili.com'] or not match:
            raise ValueError('目前原曲链接支持 B站歌手发布页的完整 BV 链接；也可由管理员提供音频文件')
        bvid = match[1]
    if not bvid:
        search_url = 'https://api.bilibili.com/x/web-interface/search/type?' + urllib.parse.urlencode({'search_type': 'video', 'keyword': query, 'page': 1})
        videos = (get_json(search_url).get('data') or {}).get('result') or []
        candidates = []
        for video in videos:
            title = html.unescape(re.sub('<[^>]+>', '', video.get('title', '')))
            author = video.get('author', '')
            if normalized(song) not in normalized(title) or not any(normalized(a['name']) in normalized(title + author) for a in track['artists']):
                continue
            if re.search(r'翻唱|cover|伴奏|教学|慢速|加速|DJ|Remix|现场|live|纯音乐', title, re.I):
                continue
            official = any(normalized(a['name']) in normalized(author) for a in track['artists'])
            official = official or bool(re.search(r'官方|official', title, re.I))
            if not official:
                continue
            try:
                parts = list(map(int, video['duration'].split(':')))
                seconds = sum(value * 60 ** index for index, value in enumerate(reversed(parts)))
            except (ValueError, KeyError):
                continue
            if abs(seconds - song_seconds) > 10:
                continue
            candidates.append((int(video.get('play', 0)), video['bvid']))
        if not candidates:
            raise ValueError('没有找到可确认版本的公开原曲；请提供原曲文件或歌手发布的链接')
        bvid = max(candidates)[1]
    view = get_json('https://api.bilibili.com/x/web-interface/view?' + urllib.parse.urlencode({'bvid': bvid}))
    if view.get('code') != 0:
        raise ValueError('公开原曲页面暂不可用')
    info = view['data']
    if normalized(song) not in normalized(info.get('title', '')):
        raise ValueError('公开音源标题与点歌曲目不一致，未生成')
    if abs(info['duration'] - song_seconds) > 10:
        raise ValueError('MV 与原曲时长差异较大，不能可靠对齐副歌')
    key = hashlib.sha256(json.dumps([song_id, bvid, start, stop]).encode()).hexdigest()[:24]
    cache = ROOT / 'song-cache'
    cache.mkdir(exist_ok=True)
    destination = cache / (key + '.wav')
    record_path = cache / (key + '.json')
    if destination.is_file() and record_path.is_file():
        record = json.loads(record_path.read_text(encoding='utf-8'))
        if record.get('sha256') == hashlib.sha256(destination.read_bytes()).hexdigest():
            return record
    play = get_json('https://api.bilibili.com/x/player/playurl?' + urllib.parse.urlencode({'bvid': bvid, 'cid': info['cid'], 'fnval': 16, 'qn': 64}))
    if play.get('code') != 0:
        raise ValueError('原曲当前不能公开播放，没有绕过登录或付费限制')
    streams = ((play.get('data') or {}).get('dash') or {}).get('audio') or []
    streams = sorted(streams, key=lambda audio: audio.get('bandwidth', 0), reverse=True)
    if not streams:
        raise ValueError('原曲没有可用的公开音轨')
    audio_url = streams[0].get('baseUrl') or streams[0].get('base_url')
    parsed = urllib.parse.urlparse(audio_url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or not any((parsed.hostname or '').endswith(domain) for domain in ['.bilivideo.com', '.bilivideo.cn']):
        raise ValueError('音轨来源不符合公开媒体域名要求')
    command = [FFMPEG, '-v', 'error', '-y', '-user_agent', HEADERS['User-Agent'], '-referer', 'https://www.bilibili.com/',
               '-ss', str(max(0, start - .08)), '-i', audio_url, '-t', str(min(MAX_SECONDS, stop - start + .08)), '-ar', '44100', '-ac', '2', str(destination)]
    result = subprocess.run(command, capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or not destination.is_file():
        raise ValueError('公开音轨截取失败，未生成假替代曲')
    record = {'source': str(destination), 'song': track['name'], 'artist': artist, 'songId': song_id,
              'sourcePage': 'https://www.bilibili.com/video/' + bvid, 'sourceAuthor': info['owner']['name'],
              'chorusStartSeconds': start, 'seconds': min(MAX_SECONDS, stop - start + .08), 'chorusMethod': method,
              'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record




def extract_positioned(url,metadata,referer,total,duration,spec):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme not in ['http','https'] or parsed.username or parsed.password or not any((parsed.hostname or '').endswith(suffix) for suffix in ['.music.126.net','.vod.126.net']):
        raise PositionError('音轨来源不符合公开媒体域名要求')
    url=urllib.parse.urlunparse(parsed._replace(scheme='https'))
    start,alignment=locate_position(spec,url,referer,metadata['sourcePage'],total,root=ROOT,ffmpeg=FFMPEG)
    start,stop=bounds(start,total,duration)
    metadata={**metadata,'positionRequest':spec,'alignment':alignment,'sourceStartSeconds':start,'chorusStartSeconds':start,'timelineAligned':True,'sourceTimeline':'selected_source','chorusMethod':'requested_'+spec['mode']}
    return extract_excerpt(url,start,stop,metadata,referer,exact=True)


if __name__ == '__main__':
    print(json.dumps(resolve_public('无人之岛', '任然'), ensure_ascii=False))
