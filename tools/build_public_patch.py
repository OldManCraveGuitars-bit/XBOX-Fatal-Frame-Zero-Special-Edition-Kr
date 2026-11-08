"""Create a source-dependent patch bundle; never bundle complete game files."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile
import zipfile
from disc import Disc

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(source, target, xdelta, destination):
    original, translated = Disc(source), Disc(target)
    oldfiles = {x['path']: x for x in original.entries if not x['directory']}
    newfiles = {x['path']: x for x in translated.entries if not x['directory']}
    if oldfiles.keys() != newfiles.keys():
        raise ValueError('File inventory mismatch')
    with Path(source).open('rb') as stream:
        source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    with Path(target).open('rb') as stream:
        target_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = dict(format='ffzero-xiso-vcdiff-1', version='V0.8',
                    source=dict(name='Fatal Frame - Zero Special Edition (Japan).iso', size=original.length, sha256=source_hash),
                    target=dict(name='Fatal-Frame-Zero-Special-Edition-Kr-V0.8.xiso.iso', size=translated.length, sha256=target_hash),
                    metadata=[], files=[])
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory() as work, zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        work = Path(work)
        metadata = [(0x10000, 2048), (translated.root_sector * 2048, translated.root_size)]
        metadata.extend((x['offset'], x['size']) for x in translated.entries if x['directory'])
        for index, (offset, size) in enumerate(metadata):
            data = translated.read(offset, size)
            payload = f'metadata/{index:04}.bin'
            archive.writestr(payload, data)
            manifest['metadata'].append(dict(offset=offset, size=size, payload=payload, sha256=sha(data)))
        modified = 0
        for index, (path, new) in enumerate(sorted(newfiles.items(), key=lambda pair: pair[1]['offset'])):
            old = oldfiles[path]
            before = original.read(old['offset'], old['size'])
            after = translated.read(new['offset'], new['size'])
            record = dict(path=path, source_offset=old['offset'], source_size=old['size'],
                          offset=new['offset'], size=new['size'])
            if before != after:
                modified += 1
                (work / 'old.bin').write_bytes(before)
                (work / 'new.bin').write_bytes(after)
                delta = work / 'delta.vcdiff'
                delta.unlink(missing_ok=True)
                subprocess.run([str(xdelta), '-e', '-9', '-A', '-D', '-s', str(work / 'old.bin'),
                                str(work / 'new.bin'), str(delta)], check=True,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                data = delta.read_bytes()
                payload = f'deltas/{modified:04}.vcdiff'
                archive.writestr(payload, data)
                record.update(source_sha256=sha(before), sha256=sha(after), delta=payload, delta_sha256=sha(data))
                print(f'{modified:02}: {path}: {len(data):,} bytes', flush=True)
            manifest['files'].append(record)
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    original.f.close()
    translated.f.close()
    print(json.dumps(dict(files=len(manifest['files']), modified=modified, bytes=destination.stat().st_size), indent=2))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--xdelta', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.target, args.xdelta, args.output)
