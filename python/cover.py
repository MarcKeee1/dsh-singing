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
from performance_library import find_performance, find_reusable_source, find_full_performance, request_spec
from voice_reference import voice_signature, REFERENCE_SECONDS
from song_position import request_position
from selection import select_range,mode_of
from cached_selection import cut_full
from instrumental_gaps import edit_mix, cached_edited, VERSION as GAP_VERSION
from singing_mix import mix_tracks, VERSION as MIX_VERSION

import numpy as np
import soundfile as sf

from runtime import ROOT, MODELS, VENDOR, CODE_DIR, CONFIG, FFMPEG, MEDIA, require_source


def main(request, cache_only=False):
    started = time.monotonic()
    if request.get('catalog') is True:
        from cache_catalog import catalog
        try:catalog_signature=voice_signature()[0]
        except (OSError,ValueError,KeyError):catalog_signature=None
        return catalog(ROOT,catalog_signature,request.get('catalogOffset',0),request.get('catalogMaxBytes',20*1024*1024))
    output = pathlib.Path(request['output']).resolve()
    if MEDIA.resolve() not in output.parents or output.suffix.lower() != '.mp3':
        raise ValueError('Output must be an MP3 inside configured outputDir')
    if request.get('cache_id'):
        from cache_catalog import materialize
        try:catalog_signature=voice_signature()[0]
        except (OSError,ValueError,KeyError):catalog_signature=None
        return materialize(ROOT,request['cache_id'],output,catalog_signature,request.get('catalogMaxBytes',20*1024*1024))
    ROOT.mkdir(parents=True,exist_ok=True)
    position=request_position(request)
    signature, settings = voice_signature()
    mode=mode_of(request)
    full=find_full_performance(ROOT,request,signature)
    if full:
        result=cut_full(*full,request,output,root=ROOT,ffmpeg=FFMPEG)
        if voice_signature()[0]!=signature:raise RuntimeError('声音正在调整，请稳定后再试')
        return result
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
    reusable = None
    if request.get('source'):
        source=require_source(request['source'])
        resolved={'song':request['title'],'artist':request.get('artist',''),'songId':'local:'+hashlib.sha256(source.read_bytes()).hexdigest(),'sourceProvider':'local','sourcePage':None}
    else:
        from resolve_song import resolve_public
        resolved=resolve_public(request['title'],request.get('artist',''),request.get('source_url',''))
        source=pathlib.Path(resolved['source']).resolve(strict=True)
    total=sf.info(source).duration
    start,stop,selection=select_range(request,source,total,resolved,root=ROOT,ffmpeg=FFMPEG)
    duration=stop-start
    resolved={**resolved,'sourceTotalSeconds':total,'sourceStartSeconds':start,'seconds':duration,
        'positionRequest':position,'selection':selection,'chorusMethod':selection['method'],'sourceComplete':mode=='full'}
    job = ROOT / 'jobs' / str(uuid.uuid4())
    job.mkdir(parents=True)
    env = {**os.environ, 'DSH_SINGING_CACHE_ROOT':str(ROOT),'DSH_SINGING_CODE_DIR':str(CODE_DIR),'PYTHONIOENCODING': 'utf-8', 'OMP_NUM_THREADS': '4',
           'TORCH_HOME': str(MODELS / 'torch'), 'PATH': str(pathlib.Path(FFMPEG).parent) + os.pathsep + os.environ.get('PATH', '')}

    def run(command, timeout=900):
        with (job / 'worker.log').open('a', encoding='utf-8') as log:
            result = subprocess.run(command, stdout=log, stderr=log, env=env, timeout=timeout,
                                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0), cwd=ROOT)
        if result.returncode:
            raise RuntimeError('Singing stage failed; diagnostic log: ' + str(job / 'worker.log'))

    normalized = job / 'source.wav'
    if reusable and start==0 and abs(sf.info(source).duration-duration)<.1:
        shutil.copyfile(source,normalized)
    else:
        reusable=None
        run([FFMPEG, '-v', 'error', '-y', '-ss', str(start), '-i', str(source), '-t', str(duration),
             '-ar', '44100', '-ac', '2', str(normalized)], max(60,duration*2))
    info = sf.info(normalized)
    if info.duration < 1:
        raise ValueError('The selected excerpt contains no usable audio')
    cache_key = hashlib.sha256((hashlib.sha256(normalized.read_bytes()).hexdigest() + signature + ':sing-v2:'+mode).encode()).hexdigest()
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
        spoken = CONFIG['referenceAudio']
        if not 3 <= sf.info(spoken).duration <= 120:
            raise ValueError('Reference voice should be 3 to 120 seconds of clean speech')
        if voice_signature()[0] != signature:
            raise RuntimeError('Speaking voice changed during reference creation; retry after it is settled')
        run([FFMPEG, '-v', 'error', '-y', '-i', str(spoken), '-t', str(REFERENCE_SECONDS), '-ar', '44100', '-ac', '1', str(reference)], 30)
    # The host serializes its GPU jobs. Also avoid interrupting external ComfyUI work.
    try:
        if not CONFIG['comfyUrl']:raise OSError('Comfy coordination disabled')
        with urllib.request.urlopen(CONFIG['comfyUrl']+'/queue', timeout=3) as response:
            queue = json.load(response)
    except OSError:
        queue = None
    if queue is not None:
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise RuntimeError('ComfyUI is busy; singing did not interrupt its job')
        if CONFIG['unloadComfy']:
            free = urllib.request.Request(CONFIG['comfyUrl']+'/free',
                data=b'{"unload_models":true,"free_memory":true}',headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(free,timeout=15) as response:response.read()
    run([sys.executable,str(CODE_DIR/'singing_worker.py'),'--job',str(job),'--reference',str(reference)],max(1200,duration*40))
    register=json.loads((job/'register.json').read_text());pitch_shift=register['semitones']
    separated=job/'separated/htdemucs/source';vocals=job/'lead/lead.wav'
    raw,sr=sf.read(vocals,always_2d=True)
    made=list((job/'converted').glob('*.wav'))
    if len(made)!=1:raise RuntimeError('Expected exactly one converted singing track')
    quality = json.loads((job / 'pitch.json').read_text(encoding='utf-8'))
    if quality.get('voicedFrames', 0) < max(200, int(info.duration * 100 * .15)):
        raise ValueError('这段可辨认的歌声太少，本次没有发送')
    if not quality.get('passed'):
        raise RuntimeError('Pitch/timing check did not pass; output withheld. See ' + str(job / 'pitch.json'))
    instrumental, _ = sf.read(separated / 'no_vocals.wav', always_2d=True)
    converted, rate = sf.read(made[0], always_2d=True)
    if sr != rate:
        raise RuntimeError('Sample rate mismatch')
    from harmony_vocal import mix_job
    mixed,mix_settings,gap_reference,sr=mix_job(job)
    master_hash=None
    if mode=='full':
        master=cached_audio.with_suffix('.master.wav')
        sf.write(master,mixed,sr,subtype='PCM_24')
        master_hash=hashlib.sha256(master.read_bytes()).hexdigest()
    mixed,gap_edits=edit_mix(mixed,gap_reference,sr)
    sf.write(job / 'mixed.wav', mixed, sr, subtype='PCM_24')
    output.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, '-v', 'error', '-y', '-i', str(job / 'mixed.wav'), '-c:a', 'libmp3lame', '-b:a', '128k',
         '-metadata', 'comment=AI singing voice conversion', str(output)], max(60,duration*2))
    if voice_signature()[0]!=signature:raise RuntimeError('声音正在调整，请稳定后再试')
    result = {'ok': True, 'path': str(output), 'song': str(request.get('title', ''))[:160],
              'seconds': round(len(mixed)/sr, 2), 'quality': quality, 'voiceSignature': signature,
              'gapEditVersion': GAP_VERSION, 'gapEdits': gap_edits, 'mixVersion': MIX_VERSION, 'mixSettings': mix_settings,
              'voiceSettings': settings, 'pitchRegister':register,'stages':json.loads((job/'stages.json').read_text()),'elapsedSeconds': round(time.monotonic() - started, 2),
              'job': str(job), 'sentToQQ': False, 'sourceStemsReused':json.loads((job/'stages.json').read_text()).get('stemCacheHit',False)}
    result['harmonyProcessing']=result['stages']['harmonyProcessing']
    result['leadVocal']=json.loads((job/'lead/lead.json').read_text(encoding='utf-8'))
    result['rawVocalSha256']=hashlib.sha256((separated/'vocals.wav').read_bytes()).hexdigest()
    result['generationElapsedSeconds']=result['elapsedSeconds']
    result.update({'masterSha256':master_hash,'normalizedSha256':hashlib.sha256(normalized.read_bytes()).hexdigest(),'vocalSha256':hashlib.sha256((separated/'vocals.wav').read_bytes()).hexdigest(),'sourceInfo': resolved, 'cacheHit': False, 'requestSpec': request_spec(request), 'audioSha256': hashlib.sha256(output.read_bytes()).hexdigest()})
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
        request=json.loads(pathlib.Path(args.request).read_text(encoding='utf-8'))
        ROOT.mkdir(parents=True,exist_ok=True)
        if args.cache_only:
            result=main(request,cache_only=True)
        else:
            from filelock import FileLock
            with FileLock(str(ROOT/'.worker.lock'),timeout=-1):result=main(request)
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
        from source_choice import SourceChoiceRequired
        if isinstance(error,SourceChoiceRequired):result.update(needsConfirmation=True,alternatives=error.options,note='先自然询问用户是否接受其中一个其他或歌手未注明的版本；未同意前不下载、不演唱，不自己选歌手。用户明确选择后再传对应 source_url。')
        request_path = pathlib.Path(args.request).resolve()
        if request_path.parent == (ROOT / 'requests').resolve():
            request_path.with_suffix('.result.json').write_text(json.dumps(
                {**result, 'diagnostic': str(error), 'at': time.time()}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        raise SystemExit(1)
