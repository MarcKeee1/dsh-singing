"""Build the installable OneBot tarball without requiring npm."""
import argparse
import json
import pathlib
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

def pack(destination=None):
    package = ROOT / 'integrations/dsh-onebot-qq'
    metadata = json.loads((package / 'package.json').read_text(encoding='utf-8'))
    output = pathlib.Path(destination) if destination else ROOT / (metadata['name'] + '-' + metadata['version'] + '.tgz')
    with tarfile.open(output, 'w:gz', format=tarfile.PAX_FORMAT) as archive:
        for file in sorted(package.rglob('*')):
            if not file.is_file() or 'node_modules' in file.relative_to(package).parts:
                continue
            name = 'package/' + file.relative_to(package).as_posix()
            info = archive.gettarinfo(str(file), arcname=name)
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            with file.open('rb') as content:
                archive.addfile(info, content)
    print(str(output.resolve()))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    pack(parser.parse_args().output)
