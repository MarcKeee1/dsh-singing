"""Local file -> separated vocal -> pitch-conditioned voice conversion -> QA -> mix.

The caller supplies an already authorized local audio file. No downloader,
QQ sender, or speaking configuration mutation is part of this process.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
from performance_library import find_performance, request_spec
from song_position import request_position
from instrumental_gaps import edit_mix, cached_edited, VERSION as GAP_VERSION
from singing_mix import mix_tracks, VERSION as MIX_VERSION

import numpy as np
import soundfile as sf

from runtime_config import ROOT, FFMPEG, TTS_PY, TTS_SCRIPT, VOICE_CONFIG, MEDIA, REFERENCE_AUDIO


def voice_signature():
    if REFERENCE_AUDIO is not None:
        if not REFERENCE_AUDIO.is_file():
            raise ValueError('Configured reference audio was not found')
        digest = hashlib.sha256(REFERENCE_AUDIO.read_bytes()).hexdigest()
        return digest, {'mode': 'reference_audio'}
    config = json.loads(VOICE_CONFIG.read_text(encoding='utf-8'))
    # Excludes API keys and transport credentials. Never write the full config.
    settings = {k: config.get(k) for k in ['model', 'voice_id', 'speed', 'pitch', 'emotion']}
    digest = hashlib.sha256(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return digest, settings


def main(request, cache_only=False):
    started = time.monotonic()
    output = pathlib.Path(request['output']).resolve()
    if MEDIA.resolve() not in output.parents or output.suffix.lower() != '.mp3':
        raise ValueError('Output must be an MP3 in the QQ voice media directory')
    position=request_position(request)
    signature, settings = voice_signature()
    existing = find_performance(ROOT, request, signature)
    if existing:
        audio, record = existing
        audio, record = cached_edited(audio, record, ROOT, FFMPEG)
        if voice_signature()[0] != signature:
            raise RuntimeError('声音正在调整，请稳定后再试')
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(audio, output)
        return {**record, 'path': str(output), 'song': str(request.get('title', ''))[:160],
                'cacheHit': True, 'cacheMode': 'performance_library',
                'elapsedSeconds': round(time.monotonic() - started, 2), 'sentToQQ': False}
    if cache_only:
        return {'ok': True, 'cacheMiss': True}
    resolved = None
    if request.get('source'):
        source = pathlib.Path(request['source']).resolve(strict=True)
    else:
        from resolve_song import resolve_public
        resolved = resolve_public(request['title'], request.get('artist', ''), request.get('duration'), request.get('chorus_hint', ''), request.get('source_url', ''), position['startSeconds'] if position and position['mode']=='seconds' else None,request.get('lyric_occurrence',1))
        source = pathlib.Path(resolved['source']).resolve(strict=True)
    start = float(request.get('start') or 0) if request.get('source') else 0
    if request.get('source') and position and position['mode']=='lyric':
        from song_position import locate_position
        total=sf.info(source).duration
        start,_=locate_position(position,str(source),'',hashlib.sha256(source.read_bytes()).hexdigest(),total,root=ROOT,ffmpeg=FFMPEG)
    requested_duration = request.get('duration')
    duration = min(float(requested_duration if requested_duration is not None else (resolved['seconds'] if resolved else 60)), resolved['seconds'] if resolved else 90)
    if request.get('source') and position:
        from song_position import bounds
        start,stop=bounds(start,sf.info(source).duration,requested_duration)
        duration=stop-start
    if not 0 <= start <= 7200 or not 1 <= duration <= 90:
        raise ValueError('Invalid excerpt start or duration (maximum 90 seconds)')
    job = ROOT / 'jobs' / str(uuid.uuid4())
    job.mkdir(parents=True)
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'OMP_NUM_THREADS': '4',
           'TORCH_HOME': str(ROOT / 'models/torch'), 'PATH': str(pathlib.Path(FFMPEG).parent) + os.pathsep + os.environ.get('PATH', '')}

    def run(command, timeout=900):
        with (job / 'worker.log').open('a', encoding='utf-8') as log:
            result = subprocess.run(command, stdout=log, stderr=log, env=env, timeout=timeout,
                                    creationflags=subprocess.CREATE_NO_WINDOW, cwd=ROOT)
        if result.returncode:
            raise RuntimeError('Singing stage failed; diagnostic log: ' + str(job / 'worker.log'))

    normalized = job / 'source.wav'
    run([FFMPEG, '-v', 'error', '-y', '-ss', str(start), '-i', str(source), '-t', str(duration),
         '-ar', '44100', '-ac', '2', str(normalized)], 60)
    info = sf.info(normalized)
    if info.duration < 1:
        raise ValueError('The selected excerpt contains no usable audio')
    cache_key = hashlib.sha256((hashlib.sha256(normalized.read_bytes()).hexdigest() + signature + ':sing-v1').encode()).hexdigest()
    performance = ROOT / 'performance-cache'
    performance.mkdir(exist_ok=True)
    cached_audio, cached_record = performance / (cache_key + '.mp3'), performance / (cache_key + '.json')
    if cached_audio.is_file() and cached_record.is_file():
        try:
            cached = json.loads(cached_record.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            cached = {}
        if (cached.get('quality', {}).get('passed')
                and cached.get('quality', {}).get('voicedFrames', 0) >= max(200, int(info.duration * 100 * .15))
                and hashlib.sha256(cached_audio.read_bytes()).hexdigest() == cached.get('audioSha256')):
            if resolved:
                cached['sourceInfo'] = resolved
            cached['requestSpec']=request_spec(request)
            cached_record.write_text(json.dumps(cached,ensure_ascii=False,indent=2),encoding='utf-8')
            selected_audio,cached=cached_edited(cached_audio,cached,ROOT,FFMPEG)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(selected_audio, output)
            cached.update({'path': str(output), 'cacheHit': True, 'cacheMode': 'exact_audio', 'elapsedSeconds': round(time.monotonic() - started, 2), 'sentToQQ': False})
            return cached
    cache = ROOT / 'references'
    cache.mkdir(exist_ok=True)
    reference = cache / (signature + '.wav')
    if not reference.is_file():
        spoken = job / 'reference.mp3'
        if REFERENCE_AUDIO is not None:
            spoken = REFERENCE_AUDIO
        else:
            run([TTS_PY, TTS_SCRIPT, '嗯，知道了。你先说，我听着。外面风很轻，窗边有一点阳光。别急，我就在这里。', '--out', str(spoken), '--json'], 75)
        if voice_signature()[0] != signature:
            raise RuntimeError('Speaking voice changed during reference creation; retry after it is settled')
        run([FFMPEG, '-v', 'error', '-y', '-i', str(spoken), '-t', '8', '-ar', '44100', '-ac', '1', str(reference)], 30)
    run([sys.executable, '-m', 'demucs.separate', '-n', 'htdemucs', '--two-stems', 'vocals',
         '--shifts', '0', '--segment', '7', '-d', 'cpu', '-o', str(job / 'separated'), str(normalized)], 1200)
    separated = job / 'separated/htdemucs/source'
    vocals = separated / 'vocals.wav'
    raw, sr = sf.read(vocals, always_2d=True)
    if np.sqrt(np.mean(raw ** 2)) < 0.001:
        raise ValueError('This excerpt contains too little singing; choose an actual vocal passage')
    # The host serializes its GPU jobs. Also avoid interrupting external ComfyUI work.
    try:
        with urllib.request.urlopen('http://127.0.0.1:8188/queue', timeout=3) as response:
            queue = json.load(response)
    except OSError:
        queue = None
    if queue is not None:
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise RuntimeError('ComfyUI is busy; singing did not interrupt its job')
        free = urllib.request.Request('http://127.0.0.1:8188/free',
            data=b'{"unload_models":true,"free_memory":true}', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(free, timeout=15) as response:
            response.read()
    run([sys.executable, str(ROOT / 'run-seed.py'), '--source', str(vocals), '--target', str(reference),
         '--outdir', str(job / 'converted'), '--steps', '40'], 1200)
    made = list((job / 'converted').glob('*.wav'))
    if len(made) != 1:
        raise RuntimeError('Expected exactly one converted singing track')
    run([sys.executable, str(ROOT / 'pitch_check.py'), '--source', str(vocals), '--converted', str(made[0]), '--out', str(job / 'pitch.json')], 300)
    quality = json.loads((job / 'pitch.json').read_text(encoding='utf-8'))
    if quality.get('voicedFrames', 0) < max(200, int(info.duration * 100 * .15)):
        raise ValueError('这段可辨认的歌声太少，本次没有发送')
    if not quality.get('passed'):
        raise RuntimeError('Pitch/timing check did not pass; output withheld. See ' + str(job / 'pitch.json'))
    instrumental, _ = sf.read(separated / 'no_vocals.wav', always_2d=True)
    converted, rate = sf.read(made[0], always_2d=True)
    if sr != rate:
        raise RuntimeError('Sample rate mismatch')
    mixed,mix_settings=mix_tracks(raw,instrumental,converted,sr)
    mixed,gap_edits=edit_mix(mixed,raw,sr)
    sf.write(job / 'mixed.wav', mixed, sr, subtype='PCM_24')
    output.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, '-v', 'error', '-y', '-i', str(job / 'mixed.wav'), '-c:a', 'libmp3lame', '-b:a', '128k',
         '-metadata', 'comment=AI singing voice conversion', str(output)], 60)
    result = {'ok': True, 'path': str(output), 'song': str(request.get('title', ''))[:160],
              'seconds': round(len(mixed)/sr, 2), 'quality': quality, 'voiceSignature': signature,
              'gapEditVersion': GAP_VERSION, 'gapEdits': gap_edits, 'mixVersion': MIX_VERSION, 'mixSettings': mix_settings,
              'voiceSettings': settings, 'elapsedSeconds': round(time.monotonic() - started, 2),
              'job': str(job), 'sentToQQ': False}
    result.update({'sourceInfo': resolved, 'cacheHit': False, 'requestSpec': request_spec(request), 'audioSha256': hashlib.sha256(output.read_bytes()).hexdigest()})
    (job / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(output, cached_audio)
    cached_record.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    parser.add_argument('--cache-only', action='store_true')
    args = parser.parse_args()
    try:
        result = main(json.loads(pathlib.Path(args.request).read_text(encoding='utf-8')), cache_only=args.cache_only)
        request_path = pathlib.Path(args.request).resolve()
        if not result.get('cacheMiss') and request_path.parent == (ROOT / 'requests').resolve():
            request_path.with_suffix('.result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as error:
        detail = str(error)
        if isinstance(error, urllib.error.HTTPError):
            detail = '曲库暂时无法访问；这次没有唱成，请稍后再试或提供原曲音频'
        elif isinstance(error, (TimeoutError, urllib.error.URLError)):
            detail = '查找原曲超时；这次没有唱成，请稍后再试'
        elif 'diagnostic log:' in detail:
            detail = '本地歌声处理失败，本次没有发送'
        result = {'ok': False, 'error': detail}
        request_path = pathlib.Path(args.request).resolve()
        if request_path.parent == (ROOT / 'requests').resolve():
            request_path.with_suffix('.result.json').write_text(json.dumps(
                {**result, 'diagnostic': str(error), 'at': time.time()}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        raise SystemExit(1)
