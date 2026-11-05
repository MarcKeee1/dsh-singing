"""Use a user-supplied reference; no bundled voice, account or TTS key."""
import hashlib,json
from runtime import CONFIG,CODE_DIR

REFERENCE_SECONDS=14
def voice_signature():
    reference=CONFIG['referenceAudio']
    if not reference.is_file():raise ValueError('Reference voice is missing; configure referenceAudio in backend.json')
    if reference.stat().st_size>50*1024*1024:raise ValueError('Reference voice exceeds 50 MB')
    settings={'engine':'reference_file','referenceVersion':1,'referenceSeconds':REFERENCE_SECONDS,
              'referenceSha256':hashlib.sha256(reference.read_bytes()).hexdigest(),
              'converterSha256':hashlib.sha256((CODE_DIR/'run-seed.py').read_bytes()).hexdigest()}
    return hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest(),settings
