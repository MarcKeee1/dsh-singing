"""One bounded worker for separation, pitch, conversion and QA. GPU exits with worker."""
import argparse,gc,json,os,pathlib,runpy,sys,time
from contextlib import contextmanager

def main(args):
    started=time.monotonic();timings={};status={'ok':False,'timings':timings}
    job=pathlib.Path(args.job).resolve();source=job/'source.wav';stems=job/'separated/htdemucs/source'
    @contextmanager
    def phase(name):
        t=time.monotonic()
        try:yield
        finally:timings[name]=round(time.monotonic()-t,3)
    try:
        with phase('imports'):
            import numpy as np,soundfile as sf,torch
            import runtime
            # The cover process owns these paths; useful for isolated QA too.
            if os.environ.get('DSH_SINGING_CACHE_ROOT'):runtime.ROOT=pathlib.Path(os.environ['DSH_SINGING_CACHE_ROOT']).resolve()
            if os.environ.get('DSH_SINGING_CODE_DIR'):runtime.CODE_DIR=pathlib.Path(os.environ['DSH_SINGING_CODE_DIR']).resolve()
            CODE_DIR,ROOT=runtime.CODE_DIR,runtime.ROOT
            import stem_cache,pitch_features
            from pitch_register import analyze
            from pitch_check import check
            torch.set_num_threads(4)
        with phase('separation'):
            hit=stem_cache.restore(ROOT,source,stems)
            status['stemCacheHit']=hit
            if not hit:
                from demucs.separate import main as separate
                device='cuda' if torch.cuda.is_available() else 'cpu'
                command=['-n','htdemucs','--two-stems','vocals','--shifts','0','--segment','7','-o',str(job/'separated'),str(source)]
                try:separate(command+['-d',device])
                except torch.cuda.OutOfMemoryError:
                    gc.collect();torch.cuda.empty_cache();device='cpu';separate(command+['-d','cpu'])
                status['separationDevice']=device
                stem_cache.store(ROOT,source,stems)
            gc.collect();torch.cuda.empty_cache()
        with phase('leadSeparation'):
            from lead_vocal import prepare
            vocals,lead_info=prepare(ROOT,stems/'vocals.wav',job/'lead',CODE_DIR)
            status['leadVocal']=lead_info
        if np.sqrt(np.mean(sf.read(vocals,always_2d=True)[0]**2))<.001:raise ValueError('This excerpt contains too little singing')
        with phase('harmonyPreparation'):
            from harmony_vocal import prepare as prepare_harmony
            harmony,harmony_info=prepare_harmony(stems/'vocals.wav',vocals,job/'lead')
            status['harmonyProcessing']=harmony_info
        with phase('register'):
            register=analyze(vocals,args.reference)
            if not runtime.CONFIG.get('autoOctave',True):register.update(semitones=0,reason='disabled_in_plugin_settings')
            (job/'register.json').write_text(json.dumps(register),encoding='utf-8')
        with phase('conversion'):
            previous=sys.argv[:];cwd=os.getcwd()
            try:
                sys.argv=[str(CODE_DIR/'convert_tracks.py'),'--source',str(vocals),'--target',args.reference,'--outdir',str(job/'converted'),'--pitch-shift',str(register['semitones'])]
                if harmony:
                    sys.argv+=['--harmony-source',str(harmony),'--harmony-outdir',str(job/'harmony-converted')]
                runpy.run_path(str(CODE_DIR/'convert_tracks.py'),run_name='__main__')
            finally:sys.argv=previous;os.chdir(cwd)
            gc.collect();torch.cuda.empty_cache()
        made=list((job/'converted').glob('*.wav'))
        if len(made)!=1:raise RuntimeError('Expected one converted audio')
        with phase('quality'):
            quality=check(vocals,made[0],register['semitones'])
            (job/'pitch.json').write_text(json.dumps(quality),encoding='utf-8')
        if harmony:
            with phase('harmonyQuality'):
                converted_harmony=list((job/'harmony-converted').glob('*.wav'))
                if len(converted_harmony)!=1:raise RuntimeError('Expected one converted harmony')
                harmony_quality=check(harmony,converted_harmony[0],register['semitones'])
                (job/'harmony-pitch.json').write_text(json.dumps(harmony_quality),encoding='utf-8')
                if not harmony_quality['passed']:raise RuntimeError('Harmony pitch/timing QA failed')
                status['harmonyProcessing']['quality']=harmony_quality
        status.update(ok=True,pitchCache=dict(pitch_features.stats))
    except BaseException as error:
        status['errorType']=type(error).__name__;raise
    finally:
        status['elapsedSeconds']=round(time.monotonic()-started,3)
        (job/'stages.json').write_text(json.dumps(status,indent=2),encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True);parser.add_argument('--reference',required=True)
    main(parser.parse_args())
