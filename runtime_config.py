"""Local runtime paths. Credentials and voice recordings stay outside Git."""
import os
from pathlib import Path

ROOT = Path(os.environ.get('DSH_SINGING_ROOT', Path(__file__).resolve().parent)).expanduser().resolve()
DSH_HOME = Path(os.environ.get('DSH_HOME', Path.home() / '.dsh')).expanduser().resolve()
VOICE_ROOT = Path(os.environ.get('DSH_TTS_ROOT', DSH_HOME / 'voice-local')).expanduser().resolve()
FFMPEG = os.environ.get('DSH_FFMPEG', 'ffmpeg')
TTS_PY = os.environ.get('DSH_TTS_PYTHON', str(VOICE_ROOT / '.venv-cosy/Scripts/python.exe'))
TTS_SCRIPT = os.environ.get('DSH_TTS_SCRIPT', str(VOICE_ROOT / 'tts.py'))
VOICE_CONFIG = Path(os.environ.get('DSH_VOICE_CONFIG', VOICE_ROOT / 'minimax.json')).expanduser().resolve()
MEDIA = DSH_HOME / 'media/onebot/voice'
REFERENCE_AUDIO = Path(os.environ['DSH_SINGING_REFERENCE']).expanduser().resolve() if os.environ.get('DSH_SINGING_REFERENCE') else None
