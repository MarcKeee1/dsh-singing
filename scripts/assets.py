"""Pinned, checksum-verified dependencies. No credentials or private media."""
import hashlib,json,pathlib,shutil,urllib.request,urllib.error,zipfile,subprocess
PROJECT=pathlib.Path(__file__).resolve().parents[1]

def sha256(path):
    with pathlib.Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def fetch(url,target,expected):
    target=pathlib.Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file() and sha256(target)==expected:return False
    partial=target.with_suffix(target.suffix+'.part')
    try:
        try:
            with urllib.request.urlopen(url,timeout=60) as response,partial.open('wb') as out:
                shutil.copyfileobj(response,out,1024*1024)
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError:
            # Windows' native TLS stack sometimes handles the system proxy
            # better than Python. Keep certificate checking and HTTPS enabled.
            curl=shutil.which('curl.exe') or shutil.which('curl')
            if not curl:raise
            subprocess.run([curl,'--fail','--location','--proto','=https','--connect-timeout','15','--max-time','1800',url,'--output',str(partial)],check=True,timeout=1810,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if sha256(partial)!=expected:raise ValueError('Checksum mismatch: '+target.name)
        partial.replace(target)
    finally:partial.unlink(missing_ok=True)
    return True

def model_path(root,item):
    return pathlib.Path(root)/(item.get('relativePath') or item['repo'].replace('/','--')+'/'+item['filename'])

def install_models(root):
    for item in json.loads((PROJECT/'models.lock.json').read_text(encoding='utf-8')):
        target=model_path(root,item)
        print('Checking model: '+item['filename'],flush=True)
        fetch(item['url'],target,item['sha256'])

def install_vendor(data):
    lock=json.loads((PROJECT/'vendor.lock.json').read_text(encoding='utf-8'))
    data=pathlib.Path(data);target=data/'vendor/seed-vc';marker=target/'.dsh-pinned.json'
    if marker.is_file():
        existing=json.loads(marker.read_text())
        if existing.get('revision')==lock['revision'] and all(hashlib.sha256((target/e['path']).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==e['patchedSha256'] for e in lock['overrides']):return target
    if target.exists():raise ValueError('Existing vendor directory is not the verified installation; move it aside before reinstalling')
    archive=data/'downloads/seed-vc.zip';fetch(lock['url'],archive,lock['sha256'])
    stage=data/'vendor/.seed-vc-extract'
    if stage.exists():raise ValueError('Incomplete vendor extraction exists; inspect '+str(stage))
    stage.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            parts=pathlib.PurePosixPath(entry.filename).parts
            if not parts or any(p in ('..','') for p in parts) or pathlib.PurePosixPath(entry.filename).is_absolute():raise ValueError('Unsafe vendor archive path')
            if (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('Vendor archive contains a symlink')
            destination=stage.joinpath(*parts)
            if not destination.resolve().is_relative_to(stage.resolve()):raise ValueError('Vendor path escaped extraction directory')
        z.extractall(stage)
    folders=list(stage.iterdir())
    if len(folders)!=1 or not folders[0].is_dir():raise ValueError('Unexpected vendor archive layout')
    unpacked=folders[0]
    for entry in lock['overrides']:
        file=unpacked/entry['path'];original=file.read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(original).hexdigest()!=entry['originalSha256']:raise ValueError('Vendor patch base changed: '+entry['path'])
        patched=(PROJECT/'vendor-overrides/seed-vc'/entry['path']).read_bytes()
        if hashlib.sha256(patched.replace(b'\r\n',b'\n')).hexdigest()!=entry['patchedSha256']:raise ValueError('Vendor override checksum mismatch')
        file.write_bytes(patched)
    unpacked.rename(target);stage.rmdir()
    marker.write_text(json.dumps({'revision':lock['revision']}),encoding='utf-8')
    return target
