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
    return {k: request.get(k) for k in ('title', 'artist', 'duration', 'chorus_hint', 'source_url', 'start', 'positionVersion', 'lyric_occurrence')}


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
    duration = request.get('duration')
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
            if (record.get('ok') is not True or record.get('voiceSignature') != signature
                    or key(source.get('song', '')) != title
                    or not key(source.get('artist', '')) or not source.get('songId')
                    or not math.isfinite(seconds) or not 5 <= seconds <= 90
                    or quality.get('passed') is not True
                    or quality.get('voicedFrames', 0) < max(200, int(seconds * 100 * .15))):
                continue
            if artist and artist_key(source['artist']) != artist:
                continue
            if prefer_bilibili(request.get('artist','')) and urllib.parse.urlparse(source.get('sourcePage','')).hostname not in {'www.bilibili.com','bilibili.com'}:
                continue
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
                exact_request = previous.get('duration') is not None and abs(float(previous['duration']) - float(duration)) < .001
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
    if len({candidate[0] for candidate in candidates}) > 1:
        return None
    if not candidates:
        return None
    selected = max(candidates, key=lambda x: (x[1], x[2], x[3]))
    return selected[4], selected[5]
