"""Reuse verified performances before source lookup or GPU work.

Only reads the local performance cache; filenames, voice, version identity,
requested excerpt constraints, QA and output hashes must all agree.
"""
import hashlib
import json
import math
import pathlib
import re
import unicodedata
import urllib.parse
from song_identity import name_key, artist_key, prefer_bilibili
from song_position import request_position, PositionError


def key(text):
    return name_key(text)


def request_spec(request):
    return {k: request.get(k) for k in ('title', 'artist', 'mode', 'duration', 'chorus_hint', 'source_url', 'source', 'start', 'positionVersion', 'lyric_occurrence')}


def original_request(record, requests):
    if isinstance(record.get('requestSpec'), dict):
        return record['requestSpec']
    # Legacy records point to their original generated output. Only a UUID is
    # used to access the known requests directory; never trust an arbitrary path.
    match = re.fullmatch(r'sing-([0-9a-f-]{36})\.mp3', pathlib.PureWindowsPath(record.get('path', '')).name)
    if match:
        try:
            value = json.loads((requests / (match[1] + '.json')).read_text(encoding='utf-8'))
            return request_spec(value)
        except (OSError, ValueError, TypeError):
            pass
    return {}


def find_performance(root, request, signature):
    if request.get('source'):
        return None
    try:position=request_position(request)
    except (ValueError,TypeError):return None
    title, artist = key(request.get('title', '')), artist_key(request.get('artist', ''))
    if not title:
        return None
    from selection import mode_of
    duration = request.get('duration')
    if duration is None:duration={'excerpt':45,'long':90}.get(mode_of(request))
    hint = key(request.get('chorus_hint') or '')
    source_url = str(request.get('source_url') or '')
    directory = root / 'performance-cache'
    candidates = []
    for file in directory.glob('*.json'):
        if not re.fullmatch(r'[0-9a-f]{64}\.json', file.name):
            continue
        try:
            record = json.loads(file.read_text(encoding='utf-8'))
            source = record.get('sourceInfo') or {}
            seconds = float(record['seconds'])
            quality = record.get('quality') or {}
            if source.get('sourceProvider')=='local':continue
            if (record.get('ok') is not True or record.get('voiceSignature') != signature
                    or key(source.get('song', '')) != title
                    or not key(source.get('artist', '')) or not source.get('songId')
                    or not math.isfinite(seconds) or seconds < 5
                    or quality.get('passed') is not True
                    or quality.get('voicedFrames', 0) < max(200, int(seconds * 100 * .15))):
                continue
            if artist and artist_key(source['artist']) != artist:
                continue
            from selection import mode_of
            if mode_of(request)!=mode_of(record.get('requestSpec') or {}):continue
            if position and source.get('positionRequest')!=position:
                continue
            previous = original_request(record, root / 'requests')
            if hint and key(previous.get('chorus_hint') or '') != hint:
                continue
            if source_url and str(previous.get('source_url') or '') != source_url:
                continue
            if duration is not None:
                # A request with a known duration can end at an earlier lyric
                # boundary. Without that provenance require the actual length.
                previous_duration=previous.get('duration')
                if previous_duration is None:
                    previous_duration={'excerpt':45}.get(mode_of(previous))
                    if mode_of(previous)=='long':previous_duration=(source.get('selection') or {}).get('softTargetSeconds')
                exact_request = previous_duration is not None and abs(float(previous_duration) - float(duration)) < .001
                if not exact_request and abs(seconds - float(duration)) > .5:
                    continue
                if seconds > float(duration) + .5:
                    continue
            audio = file.with_suffix('.mp3')
            if audio.resolve().parent != directory.resolve() or not audio.is_file():
                continue
            if hashlib.sha256(audio.read_bytes()).hexdigest() != record.get('audioSha256'):
                continue
            identity = (str(source['songId']), artist_key(source['artist']))
            complete = 'complete_section' in source.get('chorusMethod', '')
            candidates.append((identity, complete, seconds, file.stat().st_mtime, audio, record))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    # Omitted artist must not silently select between different recordings.
    # Multiple historical IDs may point to the exact same verified recording.
    if (len({candidate[0] for candidate in candidates}) > 1
            and len({candidate[5]['audioSha256'] for candidate in candidates}) > 1):
        return None
    if not candidates:
        return None
    selected = max(candidates, key=lambda x: (x[1], x[2], x[3]))
    return selected[4], selected[5]


def find_reusable_source(root, request):
    """Reuse only an exact matched, verified song excerpt when the voice changes."""
    signatures=set()
    for file in (root/'performance-cache').glob('*.json'):
        try:
            value=json.loads(file.read_text(encoding='utf-8')).get('voiceSignature')
            if isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value):signatures.add(value)
        except (OSError,ValueError,TypeError):continue
    for signature in sorted(signatures):
        match=find_performance(root,request,signature)
        if not match:continue
        record=match[1]
        job=pathlib.Path(record.get('job','')).resolve()
        if job.parent!=(root/'jobs').resolve() or not re.fullmatch(r'[0-9a-f-]{36}',job.name):continue
        files=[job/'source.wav',job/'separated/htdemucs/source/vocals.wav',job/'separated/htdemucs/source/no_vocals.wav']
        if all(f.is_file() for f in files):return {'source':files[0],'job':job,'sourceInfo':record['sourceInfo']}
    return None


def find_full_performance(root,request,signature):
    """A full master preserves original timestamps even if its playback has gap edits."""
    matches=[]
    local_hash=None
    if request.get('source'):
        from runtime import require_source
        local_hash='local:'+hashlib.sha256(require_source(request['source']).read_bytes()).hexdigest()
    for file in (root/'performance-cache').glob('*.json'):
        if not re.fullmatch(r'[0-9a-f]{64}\.json',file.name):continue
        try:
            record=json.loads(file.read_text(encoding='utf-8'));source=record.get('sourceInfo') or {}
            if record.get('voiceSignature')!=signature or not record.get('quality',{}).get('passed') or not source.get('sourceComplete'):continue
            if key(source.get('song',''))!=key(request.get('title','')):continue
            if request.get('artist') and artist_key(source.get('artist',''))!=artist_key(request['artist']):continue
            if local_hash and source.get('songId')!=local_hash:continue
            if not local_hash and source.get('sourceProvider')=='local':continue
            if request.get('source_url') and request['source_url']!=(record.get('requestSpec') or {}).get('source_url'):continue
            master=file.with_suffix('.master.wav')
            if not master.is_file() or hashlib.sha256(master.read_bytes()).hexdigest()!=record.get('masterSha256'):continue
            job=pathlib.Path(record.get('job','')).resolve()
            if job.parent!=(root/'jobs').resolve() or not re.fullmatch(r'[0-9a-f-]{36}',job.name):continue
            original=job/'source.wav';vocals=job/'separated/htdemucs/source/vocals.wav'
            if not original.is_file() or not vocals.is_file():continue
            if hashlib.sha256(original.read_bytes()).hexdigest()!=record.get('normalizedSha256'):continue
            if hashlib.sha256(vocals.read_bytes()).hexdigest()!=record.get('vocalSha256'):continue
            matches.append((file.stat().st_mtime,master,record))
        except (OSError,ValueError,TypeError,KeyError):continue
    if len({r[2]['sourceInfo']['songId'] for r in matches})>1:return None
    if not matches:return None
    selected=max(matches,key=lambda item:item[0]);return selected[1],selected[2]
