"""Check a configured backend without synthesizing or sending any audio."""
import argparse,importlib.util,json,os,pathlib,subprocess,sys
from assets import PROJECT,model_path,sha256
def check(config_path,full=False):
    os.environ['DSH_SINGING_CONFIG']=str(pathlib.Path(config_path).expanduser().resolve())
    sys.path.insert(0,str(PROJECT/'python'));checks={};details=[]
    try:
        from runtime import CONFIG,ROOT,MODELS,VENDOR,FFMPEG
        checks['config']=True
        done=subprocess.run([FFMPEG,'-version'],capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));checks['ffmpeg']=done.returncode==0
        checks['python311']=sys.version_info[:2]==(3,11)
        missing=[name for name in ['torch','torchaudio','demucs','transformers','librosa','soundfile','opencc','yaml','filelock','torchvision'] if importlib.util.find_spec(name) is None]
        checks['dependencies']=not missing
        if missing:details.append({'missingModules':missing})
        checks['leadEnvironment']=CONFIG['leadPython'].is_file()
        if checks['leadEnvironment']:
            probe=subprocess.run([str(CONFIG['leadPython']),'-c','import audio_separator,onnxruntime,onnx,onnx2torch,torchvision'],capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            checks['leadEnvironment']=probe.returncode==0
        if not checks['leadEnvironment']:details.append({'leadEnvironment':'Missing or incomplete; rerun scripts/setup.py'})
        manifest=json.loads((PROJECT/'models.lock.json').read_text())
        absent=[entry['filename'] for entry in manifest if not model_path(MODELS,entry).is_file() or model_path(MODELS,entry).stat().st_size!=entry['bytes']]
        checks['models']=not absent
        if absent:details.append({'missingOrIncompleteModels':absent})
        if full and not absent:
            wrong=[entry['filename'] for entry in manifest if sha256(model_path(MODELS,entry))!=entry['sha256']]
            checks['modelHashes']=not wrong
            if wrong:details.append({'checksumMismatches':wrong})
        lock=json.loads((PROJECT/'vendor.lock.json').read_text())
        checks['seedVc']=(VENDOR/'inference.py').is_file() and (VENDOR/'.dsh-pinned.json').is_file()
        if checks['seedVc']:
            import hashlib
            checks['seedVc']=all(hashlib.sha256((VENDOR/e['path']).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==e['patchedSha256'] for e in lock['overrides'])
        checks['modelConfig']=(ROOT/'singing-local.yml').is_file()
        checks['referenceVoice']=CONFIG['referenceAudio'].is_file()
        if checks['dependencies']:
            import soundfile as sf,torch
            checks['referenceVoice']=checks['referenceVoice'] and 3<=sf.info(CONFIG['referenceAudio']).duration<=120
            details.append({'torch':torch.__version__,'cuda':torch.cuda.is_available(),'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU (slow)'})
    except Exception as error:checks['inspection']=False;details.append({'error':str(error)})
    return {'ok':bool(checks) and all(checks.values()),'checks':checks,'details':details,'sentToQQ':False}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',default=str(pathlib.Path(os.environ.get('DSH_HOME',str(pathlib.Path.home()/'.dsh')))/'singing/backend.json'));parser.add_argument('--full',action='store_true');args=parser.parse_args()
    result=check(args.config,args.full);print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['ok'] else 1)
