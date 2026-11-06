"""Borrow timed lyrics only after the actual recordings match at three locations."""
import hashlib
import json
import math
import pathlib
import subprocess
import uuid

from song_identity import name_key, artist_key

VERSION = 'recording-lyrics-v1'
MIN_SCORE = .85
MAX_DRIFT = .12
MAX_OFFSET = 15


def digest(path):
    result = hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Lyrics cache exceeds its resource limit')
    data = json.loads(path.read_text('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Invalid lyrics cache')
    return data


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False), 'utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def timed_lines(rows, total, offset=0):
    result = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            continue
        try:
            stamp = float(row[0]) + offset
        except (TypeError, ValueError):
            continue
        if math.isfinite(stamp) and 0 <= stamp < total and isinstance(row[1], str) and name_key(row[1]):
            result.append((stamp, row[1]))
    return sorted(set(result))


def mono_window(path, start, length, rate=2000):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    with sf.SoundFile(path) as stream:
        frame = max(0, round(start * stream.samplerate))
        stream.seek(frame)
        audio = stream.read(round(length * stream.samplerate), dtype='float32', always_2d=True)
        sr = stream.samplerate
    if not len(audio):
        raise ValueError('Empty alignment window')
    divisor = math.gcd(sr, rate)
    samples = resample_poly(np.mean(audio, axis=1), rate // divisor, sr // divisor)
    samples -= np.mean(samples)
    return samples, frame / sr


def align_recordings(source, reference):
    import numpy as np
    import soundfile as sf
    from scipy.signal import correlate, fftconvolve
    total, ref_total = sf.info(source).duration, sf.info(reference).duration
    if min(total, ref_total) < 35 or abs(total - ref_total) > MAX_OFFSET * 2 + 2:
        return None
    rate = 2000
    length = min(12, min(total, ref_total) * .12)
    windows = []
    for fraction in (.18, .45, .72):
        begin = ref_total * fraction
        clip, ref_start = mono_window(reference, begin, length, rate)
        first = max(0, begin - MAX_OFFSET)
        samples, source_start = mono_window(source, first, min(total - first, length + 2 * MAX_OFFSET), rate)
        power = float(np.sum(clip.astype('float64') ** 2))
        if len(samples) < len(clip) or power < len(clip) * 1e-8:
            return None
        curve = correlate(samples, clip, mode='valid', method='fft')
        energy = fftconvolve(samples.astype('float64') ** 2, np.ones(len(clip)), mode='valid')
        scores = np.abs(curve) / np.sqrt(np.maximum(energy, 1e-15) * power)
        peak = int(np.argmax(scores))
        score = min(1.0, float(scores[peak]))
        offset = source_start + peak / rate - ref_start
        if not math.isfinite(score + offset) or score < MIN_SCORE or abs(offset) > MAX_OFFSET + .01:
            return None
        windows.append({'referenceSeconds': round(ref_start, 4), 'offsetSeconds': round(offset, 4),
                        'correlation': round(score, 4)})
    offsets = [window['offsetSeconds'] for window in windows]
    if max(offsets) - min(offsets) > MAX_DRIFT:
        return None
    return {'version': VERSION, 'method': 'verified_recording_correlation',
            'offsetSeconds': round(float(np.median(offsets)), 4), 'matchedWindows': windows}


def valid_alignment(value):
    try:
        windows = value['matchedWindows']
        offsets = [float(window['offsetSeconds']) for window in windows]
        return (value['version'] == VERSION and value['method'] == 'verified_recording_correlation'
                and len(windows) == 3 and all(math.isfinite(x) and abs(x) <= MAX_OFFSET + .01 for x in offsets)
                and max(offsets) - min(offsets) <= MAX_DRIFT
                and all(MIN_SCORE <= float(window['correlation']) <= 1 for window in windows)
                and abs(float(value['offsetSeconds']) - sorted(offsets)[1]) < .001)
    except (KeyError, TypeError, ValueError):
        return False


def valid_reference(record, root, song, artist):
    import soundfile as sf
    try:
        path = pathlib.Path(record['source'])
        if (record.get('sourceProvider') != 'netease' or record.get('sourceComplete') is not True
                or name_key(record.get('song', '')) != name_key(song)
                or artist_key(record.get('artist', '')) != artist_key(artist)
                or path.is_symlink() or path.resolve().parent != (root / 'song-cache').resolve()
                or path.suffix != '.wav' or digest(path) != record['sha256']):
            return False
        total = sf.info(path).duration
        return abs(total - float(record['seconds'])) < .1 and len(timed_lines(record.get('lyricLines') or [], total)) >= 4
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False


def enrich_lyrics(source, total, metadata, *, root, fetch_reference=None):
    """Preserve the chosen audio/version. Failure falls back to its own ASR."""
    song, artist = metadata.get('song', ''), metadata.get('artist', '')
    if (metadata.get('lyricLines') or metadata.get('sourceProvider') not in {'bilibili', 'netease', 'qqmusic'}
            or not song or not artist or artist in {'视频指定版本', '视频未标注歌手', '未知'}):
        return metadata
    root = pathlib.Path(root)
    try:
        import soundfile as sf
        source = pathlib.Path(source)
        if not source.is_file() or abs(sf.info(source).duration - total) > .1:
            return metadata
        sha = digest(source)
        identity = [VERSION, sha, name_key(song), artist_key(artist)]
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        cached = root / 'lyric-alignment-cache' / (key + '.json')
        if cached.is_file():
            try:
                record = read_json(cached)
                lines = timed_lines(record.get('lyricLines') or [], total)
                if (record.get('sourceSha256') == sha and record.get('version') == VERSION
                        and len(lines) >= 4 and valid_alignment(record.get('lyricsAlignment'))):
                    return {**metadata, 'lyricLines': lines, 'lyricsAlignment': record['lyricsAlignment']}
            except (OSError, ValueError, KeyError, TypeError):
                pass
        reference_key = hashlib.sha256(json.dumps([VERSION, name_key(song), artist_key(artist)], ensure_ascii=False).encode()).hexdigest()
        reference_cache = root / 'lyric-reference-cache' / (reference_key + '.json')
        reference = None
        if reference_cache.is_file():
            try:
                record = read_json(reference_cache)
                if valid_reference(record, root, song, artist):
                    reference = record
            except (OSError, ValueError, TypeError):
                pass
        if reference is None:
            if fetch_reference is None:
                from resolve_song import resolve_netease
                fetch_reference = resolve_netease
            reference = fetch_reference(song, artist)
            if not valid_reference(reference, root, song, artist):
                return metadata
            write_json(reference_cache, reference)
        alignment = align_recordings(source, reference['source'])
        if alignment is None:
            return metadata
        lines = timed_lines(reference['lyricLines'], total, alignment['offsetSeconds'])
        if len(lines) < 4:
            return metadata
        alignment['referenceSongId'] = reference['songId']
        record = {'version': VERSION, 'sourceSha256': sha, 'lyricLines': lines, 'lyricsAlignment': alignment}
        write_json(cached, record)
        return {**metadata, 'lyricLines': lines, 'lyricsAlignment': alignment}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError, subprocess.TimeoutExpired):
        # A metadata service or alternate edition must not break the original
        # selected-source ASR path, or silently replace the user's recording.
        return metadata
