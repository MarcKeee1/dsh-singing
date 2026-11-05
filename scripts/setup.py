"""Install an isolated Python backend; never modifies a DSH profile."""
import argparse,json,os,pathlib,shutil,subprocess,sys,venv
from assets import PROJECT,install_models,install_vendor

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=pathlib.Path,default=pathlib.Path(os.environ.get('DSH_HOME',str(pathlib.Path.home()/'.dsh')))/'singing')
    parser.add_argument('--models-dir',type=pathlib.Path)
    parser.add_argument('--reference-audio',type=pathlib.Path)
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--torch',choices=['cu121','cpu'],default='cu121')
    parser.add_argument('--skip-deps',action='store_true',help='Reuse an already prepared data-dir/.venv; for maintainers')
    parser.add_argument('--skip-models',action='store_true',help='Prepare environment only; doctor remains unready until models are installed')
    args=parser.parse_args()
    if sys.version_info[:2]!=(3,11):raise ValueError('Run this installer with Python 3.11 (Windows: py -3.11 scripts/setup.py)')
    ffmpeg=shutil.which(args.ffmpeg)
    if not ffmpeg:raise ValueError('Install FFmpeg first, or pass --ffmpeg with its executable path')
    data=args.data_dir.expanduser().resolve();data.mkdir(parents=True,exist_ok=True)
    envdir=data/'.venv';python=envdir/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():venv.EnvBuilder(with_pip=True).create(envdir)
    def run(*command):subprocess.run(list(map(str,command)),check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if not args.skip_deps:
        run(python,'-m','pip','install','--upgrade','pip')
        run(python,'-m','pip','install','torch==2.4.1','torchaudio==2.4.1','--index-url','https://download.pytorch.org/whl/'+args.torch)
        run(python,'-m','pip','install','-r',PROJECT/'requirements.txt','-c',PROJECT/'constraints.txt')
        run(python,'-m','pip','check')
    vendor=install_vendor(data)
    models=(args.models_dir or data/'models').expanduser().resolve()
    if not args.skip_models:install_models(models)
    config=data/'backend.json'
    current=json.loads(config.read_text(encoding='utf-8-sig')) if config.exists() else {}
    output=pathlib.Path(os.environ.get('DSH_HOME',str(pathlib.Path.home()/'.dsh')))/'media/onebot/voice'
    current.update(dataDir=str(data),modelsDir=str(models),vendorDir=str(vendor),ffmpeg=ffmpeg)
    current.setdefault('outputDir',str(output));current.setdefault('allowedSourceRoots',[])
    current.setdefault('referenceAudio',str(data/'voice/reference.wav'));current.setdefault('comfyUrl','');current.setdefault('unloadComfy',False)
    if args.reference_audio:current['referenceAudio']=str(args.reference_audio.expanduser().resolve(strict=True))
    temporary=config.with_suffix('.tmp');temporary.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(config)
    run(python,PROJECT/'scripts/prepare.py','--config',config)
    print('\nBackend prepared: '+str(config))
    print('Next: configure your referenceAudio, run doctor.py, then install the DSH .tgz.')
    print('Python: '+str(python))

if __name__=='__main__':
    try:main()
    except Exception as error:print('Setup failed: '+str(error),file=sys.stderr);raise SystemExit(1)
