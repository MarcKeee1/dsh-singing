"""Local configuration shared by the resolver and isolated model workers."""
import json,os,pathlib,shutil,math,sys

CODE_DIR=pathlib.Path(__file__).resolve().parent
PROJECT_DIR=CODE_DIR.parent
CONFIG_FILE=pathlib.Path(os.environ.get('DSH_SINGING_CONFIG',str(pathlib.Path(os.environ.get('DSH_HOME',str(pathlib.Path.home()/'.dsh')))/'singing/backend.json'))).expanduser().resolve()

def load_config(path=CONFIG_FILE):
    path=pathlib.Path(path).expanduser().resolve()
    try:config=json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:raise ValueError('Singing backend is not configured; run scripts/setup.py first') from None
    if not isinstance(config,dict):raise ValueError('Backend config must be an object')
    overrides=json.loads(os.environ.get('DSH_SINGING_UI_SETTINGS','{}'))
    allowed={'referenceAudio','autoOctave','voiceGain','musicGain','harmonyGain','shortenGaps','autoSoloGuard'}
    if not isinstance(overrides,dict) or set(overrides)-allowed:raise ValueError('Invalid plugin settings')
    config.update(overrides)
    for key in ('autoOctave','shortenGaps','autoSoloGuard'):
        config.setdefault(key,True)
        if not isinstance(config[key],bool):raise ValueError('Invalid boolean setting: '+key)
    for key,default,low,high in [('voiceGain',1.25,.1,3),('musicGain',.55,.05,2),('harmonyGain',0,0,1.5)]:
        config.setdefault(key,default);value=config[key]
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Invalid gain setting: '+key)
    def location(key,default):
        p=pathlib.Path(config.get(key) or default).expanduser()
        return p.resolve() if p.is_absolute() else (path.parent/p).resolve()
    data=location('dataDir',path.parent)
    config.update(dataDir=data,modelsDir=location('modelsDir',data/'models'),vendorDir=location('vendorDir',data/'vendor/seed-vc'),leadPython=location('leadPython',data/'.venv-lead'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')),
                  soloPython=location('soloPython',sys.executable),outputDir=location('outputDir',data/'output'),referenceAudio=location('referenceAudio',data/'voice/reference.wav'))
    ffmpeg=str(config.get('ffmpeg') or 'ffmpeg')
    executable=shutil.which(ffmpeg)
    if not executable:
        candidate=pathlib.Path(ffmpeg).expanduser()
        if not candidate.is_absolute():candidate=path.parent/candidate
        if candidate.is_file():executable=str(candidate.resolve())
    if not executable:raise ValueError('FFmpeg was not found; configure ffmpeg in backend.json')
    config['ffmpeg']=executable
    config['allowedSourceRoots']=[location('_source_root',p) for p in config.get('allowedSourceRoots',[])]
    config['comfyUrl']=str(config.get('comfyUrl') or '').rstrip('/')
    config['unloadComfy']=config.get('unloadComfy') is True
    return config

CONFIG=load_config()
ROOT=CONFIG['dataDir']
MODELS=CONFIG['modelsDir']
VENDOR=CONFIG['vendorDir']
FFMPEG=CONFIG['ffmpeg']
MEDIA=CONFIG['outputDir']
FLAGS=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0)

def require_source(path):
    file=pathlib.Path(path).expanduser().resolve(strict=True)
    if not file.is_file() or file.suffix.lower() not in {'.mp3','.wav','.flac','.m4a','.ogg','.opus','.aac'}:
        raise ValueError('Local source must be a supported audio file')
    if not any(file.is_relative_to(root) for root in CONFIG['allowedSourceRoots']):
        raise ValueError('Local source is outside configured allowedSourceRoots')
    if file.stat().st_size>100*1024*1024:raise ValueError('Local source exceeds 100 MB')
    return file
