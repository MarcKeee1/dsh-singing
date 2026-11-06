"""Use a user-supplied reference; no bundled voice, account or TTS key."""
import hashlib,json
from runtime import CONFIG,CODE_DIR

REFERENCE_SECONDS=14
def voice_signature():
    reference=CONFIG['referenceAudio']
    if not reference.is_file():raise ValueError('Reference voice is missing; configure referenceAudio in backend.json')
    if reference.stat().st_size>50*1024*1024:raise ValueError('Reference voice exceeds 50 MB')
    settings={'engine':'reference_file','referenceVersion':2,'referenceSeconds':REFERENCE_SECONDS,
              'referenceSha256':hashlib.sha256(reference.read_bytes()).hexdigest(),
              'pipelineSha256':hashlib.sha256(b''.join((CODE_DIR/name).read_bytes().replace(b'\r\n',b'\n') for name in ('convert_tracks.py','singing_worker.py','pitch_register.py','phrase_register.py','lead_worker.py','harmony_vocal.py'))).hexdigest()}
    settings['audioSettings']={key:CONFIG[key] for key in ('autoOctave','voiceGain','musicGain','harmonyGain','shortenGaps')}
    return hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest(),settings
