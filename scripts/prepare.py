import argparse,json,pathlib,yaml
parser=argparse.ArgumentParser();parser.add_argument('--config',required=True,type=pathlib.Path);args=parser.parse_args()
cfg=json.loads(args.config.read_text(encoding='utf-8-sig'));root=pathlib.Path(cfg['dataDir']);models=pathlib.Path(cfg['modelsDir'])
source=models/'Plachta--Seed-VC/config_dit_mel_seed_uvit_whisper_base_f0_44k.yml'
if source.is_file():
    settings=yaml.safe_load(source.read_text(encoding='utf-8'))
    settings['model_params']['speech_tokenizer']['name']=str(models/'openai--whisper-small')
    settings['model_params']['vocoder']['name']=str(models/'nvidia--bigvgan_v2_44khz_128band_512x')
    (root/'singing-local.yml').write_text(yaml.safe_dump(settings,allow_unicode=True),encoding='utf-8')
else:print('Model configuration is not present yet; rerun setup without --skip-models.')
