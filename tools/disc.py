"""Read-only XDVDFS inventory/extraction for Fatal Frame Zero Special Edition."""
from pathlib import Path, PurePosixPath
import argparse, collections, hashlib, json, struct

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_ISO = Path('Fatal Frame - Zero Special Edition (Japan).iso')
MAGIC = b'MICROSOFT*XBOX*MEDIA'

class Disc:
    def __init__(self, path):
        self.path = Path(path)
        self.f = self.path.open('rb')
        self.length = self.path.stat().st_size
        for base in (0, 0x18300000, 0xfd90000, 0x2080000):
            self.f.seek(base + 0x10000)
            descriptor = self.f.read(2048)
            if descriptor[:20] == MAGIC and descriptor[-20:] == MAGIC:
                self.base = base
                self.root_sector, self.root_size = struct.unpack_from('<II', descriptor, 20)
                break
        else:
            raise ValueError('No supported XDVDFS volume descriptor')
        self.entries = []
        self.walk('', self.root_sector, self.root_size)

    def read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.length:
            raise ValueError('Read outside disc')
        self.f.seek(offset)
        data = self.f.read(size)
        if len(data) != size:
            raise EOFError(offset)
        return data

    def walk(self, parent, sector, size):
        if not size:
            return
        data = self.read(self.base + sector * 2048, size)
        visited = set()
        def node(offset):
            if offset in visited or offset + 14 > size:
                raise ValueError(f'Invalid directory tree {parent}:{offset}')
            visited.add(offset)
            left, right, start, length, attrs, nlen = struct.unpack_from('<HHIIBB', data, offset)
            if offset + 14 + nlen > size:
                raise ValueError('Invalid filename length')
            name = data[offset+14:offset+14+nlen].decode('ascii')
            if not name or name in ('.', '..') or '/' in name or '\\' in name:
                raise ValueError('Unsafe filename')
            path = str(PurePosixPath(parent) / name)
            if left:
                node(left * 4)
            entry = dict(path=path, sector=start, offset=self.base+start*2048, size=length,
                         directory=bool(attrs & 0x10), table_entry_offset=self.base+sector*2048+offset)
            self.entries.append(entry)
            if entry['directory']:
                self.walk(path, start, length)
            if right:
                node(right * 4)
        node(0)

    def extract(self, entries, dest):
        for e in entries:
            if e['directory']:
                continue
            target = dest.joinpath(*PurePosixPath(e['path']).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.stat().st_size == e['size']:
                continue
            with target.open('wb') as out:
                self.f.seek(e['offset'])
                left = e['size']
                while left:
                    buf = self.f.read(min(left, 4*1024*1024))
                    if not buf:
                        raise EOFError(e['path'])
                    out.write(buf)
                    left -= len(buf)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iso', type=Path, default=DEFAULT_ISO)
    ap.add_argument('--extract', action='store_true')
    args = ap.parse_args()
    disc = Disc(args.iso)
    report = PROJECT / 'analysis'
    report.mkdir(parents=True, exist_ok=True)
    manifest = dict(source=str(args.iso), source_size=disc.length, partition_base=disc.base,
                    entries=disc.entries)
    (report/'disc_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    files = [e for e in disc.entries if not e['directory']]
    print(json.dumps(dict(partition_base=hex(disc.base), files=len(files), total_bytes=sum(e['size'] for e in files),
                          extensions=collections.Counter(PurePosixPath(e['path']).suffix.lower() for e in files)), indent=2))
    for e in files:
        print(f"{e['size']:12d} {e['path']}")
    if args.extract:
        disc.extract(files, PROJECT/'original')
        print('Extracted to', PROJECT/'original')

if __name__ == '__main__':
    main()
