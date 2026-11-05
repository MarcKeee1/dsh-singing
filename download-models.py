"""Download the exact model/tokenizer revisions listed in models.lock.json."""
import concurrent.futures
import hashlib
import json
import urllib.request
from runtime_config import ROOT

def download(entry):
    target = ROOT / 'models' / entry['repo'].replace('/', '--') / entry['filename']
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        partial = target.with_suffix(target.suffix + '.part')
        with urllib.request.urlopen(entry['url'], timeout=180) as response, partial.open('wb') as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        with partial.open('rb') as handle:
            actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        if actual != entry['sha256']:
            raise RuntimeError('Checksum mismatch: ' + entry['filename'])
        partial.replace(target)
    with target.open('rb') as handle:
        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
    if actual != entry['sha256']:
        raise RuntimeError('Checksum mismatch: ' + entry['filename'])
    print(json.dumps({'verified': entry['filename'], 'bytes': target.stat().st_size}), flush=True)
    return {**entry, 'path': str(target)}

if __name__ == '__main__':
    lock = json.loads((ROOT / 'models.lock.json').read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(download, lock))
    (ROOT / 'model-manifest.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
