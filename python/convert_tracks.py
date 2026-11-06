"""Same frozen Seed-VC recipe as run-seed; reuse loaded models across vocal tracks."""
import argparse,os,pathlib,sys,json
import torch
from runtime import ROOT,MODELS,VENDOR
def main(args):
    os.environ.update(DSH_SINGING_MODELS=str(MODELS),DSH_SINGING_MAX_SEQUENCE='2048',DSH_SINGING_CONTEXT_SECONDS='22',
                      HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    torch.set_num_threads(4);sys.path.insert(0,str(VENDOR));os.chdir(VENDOR)
    import inference
    original=inference.load_models;models=[];current={}
    profiles=json.loads(pathlib.Path(args.register_json).read_text('utf-8')).get('phraseRegister',{}) if args.register_json else {}
    if profiles:
        from pitch_features import extract
        from phrase_register import apply as apply_register
        target_f0,_=extract(args.target)
    def load_once(options):
        if not models:models.append(original(options))
        if not current.get('profile'):return models[0]
        prepared=list(models[0]);sequence=iter([target_f0,current['conditioned']])
        prepared[2]=lambda wave,thred:next(sequence).copy()
        return tuple(prepared)
    inference.load_models=load_once
    try:
        tracks=[('lead',args.source,args.outdir)]
        if args.harmony_source:tracks.append(('harmony',args.harmony_source,args.harmony_outdir))
        for label,source,outdir in tracks:
            current.clear();profile=profiles.get(label)
            if profile and profile['intervals']:
                raw,_=extract(source)
                current.update(profile=profile,conditioned=(apply_register(raw,profile,args.pitch_shift)/2**(args.pitch_shift/12)).astype('float32'))
            torch.manual_seed(20261105)
            options=argparse.Namespace(source=source,target=args.target,output=outdir,diffusion_steps=args.steps,length_adjust=1.0,
                inference_cfg_rate=args.cfg,f0_condition=True,auto_f0_adjust=False,semi_tone_shift=args.pitch_shift,
                checkpoint=str(MODELS/'Plachta--Seed-VC/DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema_v2.pth'),
                config=str(ROOT/'singing-local.yml'),fp16=torch.cuda.is_available())
            inference.main(options)
    finally:inference.load_models=original;models.clear()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--target',required=True);p.add_argument('--outdir',required=True)
    p.add_argument('--pitch-shift',type=int,choices=[0,12],default=0);p.add_argument('--harmony-source');p.add_argument('--harmony-outdir')
    p.add_argument('--steps',type=int,choices=[40,60],default=40);p.add_argument('--cfg',type=float,choices=[.7,1.0],default=.7);p.add_argument('--register-json');main(p.parse_args())
