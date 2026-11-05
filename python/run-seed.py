"""Offline Seed-VC adapter; keep melody, timing and key fixed."""
import argparse
import os
import pathlib
import runpy
import sys
import torch

from runtime import ROOT, MODELS, VENDOR
parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
parser.add_argument('--target', required=True)
parser.add_argument('--outdir', required=True)
parser.add_argument('--steps', default=40, type=int)
args = parser.parse_args()
for item in [args.source, args.target]:
    if not pathlib.Path(item).is_file():
        raise SystemExit('Missing input audio')
os.environ['DSH_SINGING_MODELS'] = str(MODELS)
os.environ['DSH_SINGING_MAX_SEQUENCE'] = '2048'
os.environ['DSH_SINGING_CONTEXT_SECONDS'] = '22'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
torch.set_num_threads(4)
torch.manual_seed(20261105)
sys.path.insert(0, str(VENDOR))
os.chdir(VENDOR)
sys.argv = [
    str(VENDOR / 'inference.py'), '--source', str(pathlib.Path(args.source).resolve()),
    '--target', str(pathlib.Path(args.target).resolve()), '--output', str(pathlib.Path(args.outdir).resolve()),
    '--checkpoint', str(MODELS / 'Plachta--Seed-VC/DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema_v2.pth'),
    '--config', str(ROOT / 'singing-local.yml'), '--f0-condition', 'True', '--auto-f0-adjust', 'False',
    '--semi-tone-shift', '0', '--length-adjust', '1.0', '--diffusion-steps', str(args.steps),
    '--inference-cfg-rate', '0.7', '--fp16', str(torch.cuda.is_available()),
]
runpy.run_path(str(VENDOR / 'inference.py'), run_name='__main__')
