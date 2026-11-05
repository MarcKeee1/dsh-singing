"""Fetch a pinned Seed-VC checkout and generate local model configuration."""
import argparse
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime_config import ROOT

SEED_COMMIT = '51383efd921027683c89e5348211d93ff12ac2a8'
SEED_URL = 'https://github.com/Plachtaa/seed-vc.git'

def prepare(warm_demucs=False):
    import yaml
    vendor = ROOT / 'vendor/seed-vc'
    if not vendor.exists():
        vendor.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--no-checkout', SEED_URL, str(vendor)], check=True)
        subprocess.run(['git', '-C', str(vendor), 'checkout', '--detach', SEED_COMMIT], check=True)
    head = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
    if head != SEED_COMMIT:
        raise RuntimeError('Existing Seed-VC checkout differs from the pinned revision; no files changed')
    patch = str(ROOT / 'patches/seed-vc-offline.patch')
    applied = subprocess.run(['git', '-C', str(vendor), 'apply', '--reverse', '--check', patch], capture_output=True).returncode == 0
    if not applied:
        subprocess.run(['git', '-C', str(vendor), 'apply', '--check', patch], check=True)
        subprocess.run(['git', '-C', str(vendor), 'apply', patch], check=True)
    original = ROOT / 'models/Plachta--Seed-VC/config_dit_mel_seed_uvit_whisper_base_f0_44k.yml'
    config = yaml.safe_load(original.read_text(encoding='utf-8'))
    config['model_params']['vocoder']['name'] = str(ROOT / 'models/nvidia--bigvgan_v2_44khz_128band_512x')
    config['model_params']['speech_tokenizer']['name'] = str(ROOT / 'models/openai--whisper-small')
    (ROOT / 'singing-local.yml').write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
    for directory in ['jobs', 'requests', 'imports', 'references', 'performance-cache']:
        (ROOT / directory).mkdir(exist_ok=True)
    if warm_demucs:
        os.environ['TORCH_HOME'] = str(ROOT / 'models/torch')
        from demucs.pretrained import get_model
        get_model('htdemucs')
    print('Seed-VC and local configuration prepared / Seed-VC 与本地配置已就绪')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--warm-demucs', action='store_true')
    prepare(parser.parse_args().warm_demucs)
