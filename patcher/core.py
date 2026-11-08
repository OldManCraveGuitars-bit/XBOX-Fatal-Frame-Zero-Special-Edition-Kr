"""Reconstruct the verified XISO using an exact original ISO and VCDIFF deltas."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile

CHUNK = 4 * 1024 * 1024


def digest(path, callback=None):
    total = Path(path).stat().st_size
    done = 0
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data := stream.read(CHUNK):
            value.update(data)
            done += len(data)
            if callback:
                callback(done / max(total, 1))
    return value.hexdigest()


def checked_member(archive, name, expected):
    data = archive.read(name)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('패치 데이터 해시 불일치: ' + name)
    return data


def validate_manifest(manifest):
    if manifest.get('format') != 'ffzero-xiso-vcdiff-1':
        raise ValueError('지원하지 않는 패치 형식입니다.')
    source_size = manifest['source']['size']
    target_size = manifest['target']['size']
    if source_size <= 0 or target_size <= 0:
        raise ValueError('잘못된 ISO 크기입니다.')
    ranges = []
    paths = set()
    for item in manifest['files']:
        if item['path'] in paths:
            raise ValueError('중복 파일 항목입니다.')
        paths.add(item['path'])
        if not (0 <= item['source_offset'] <= source_size and
                0 <= item['source_size'] <= source_size - item['source_offset']):
            raise ValueError('원본 파일 범위를 벗어납니다.')
        if not (0 <= item['offset'] <= target_size and
                0 <= item['size'] <= target_size - item['offset']):
            raise ValueError('출력 파일 범위를 벗어납니다.')
        if not item.get('delta') and item['size'] != item['source_size']:
            raise ValueError('차분 없는 파일의 크기가 다릅니다.')
        if item['size']:
            ranges.append((item['offset'], item['offset'] + item['size']))
    for item in manifest['metadata']:
        if not (0 <= item['offset'] < target_size and
                0 < item['size'] <= target_size - item['offset']):
            raise ValueError('메타데이터 범위를 벗어납니다.')
        ranges.append((item['offset'], item['offset'] + item['size']))
    ordered = sorted(ranges)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('출력 범위가 겹칩니다.')


def inspect_bundle(bundle, xdelta, bundle_sha256, xdelta_sha256):
    if digest(bundle) != bundle_sha256:
        raise ValueError('배포 패치 파일의 SHA-256이 다릅니다.')
    if digest(xdelta) != xdelta_sha256:
        raise ValueError('xdelta3 실행 파일의 SHA-256이 다릅니다.')
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        validate_manifest(manifest)
        for item in manifest['metadata']:
            data = checked_member(archive, item['payload'], item['sha256'])
            if len(data) != item['size']:
                raise ValueError('메타데이터 크기가 다릅니다.')
        for item in manifest['files']:
            if item.get('delta'):
                checked_member(archive, item['delta'], item['delta_sha256'])
    return manifest


def read_exact(stream, offset, size):
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise EOFError('원본 ISO를 끝까지 읽을 수 없습니다.')
    return data


def copy_range(source, output, item):
    source.seek(item['source_offset'])
    output.seek(item['offset'])
    remaining = item['size']
    while remaining:
        data = source.read(min(CHUNK, remaining))
        if not data:
            raise EOFError('원본 ISO를 끝까지 읽을 수 없습니다.')
        output.write(data)
        remaining -= len(data)


def apply_patch(source, destination, bundle, xdelta, bundle_sha256,
                xdelta_sha256, log=lambda value: None,
                progress=lambda value: None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('원본 ISO와 다른 출력 경로를 지정하십시오.')
    if destination.exists():
        raise FileExistsError('출력 파일이 이미 있습니다. 새 파일 이름을 지정하십시오.')
    if not destination.parent.is_dir():
        raise ValueError('출력 폴더가 없습니다.')
    manifest = inspect_bundle(bundle, xdelta, bundle_sha256, xdelta_sha256)
    if source.stat().st_size != manifest['source']['size']:
        raise ValueError('지원하는 일본판 원본 ISO와 크기가 다릅니다.')
    log('일본판 원본 ISO의 SHA-256을 확인합니다...')
    if digest(source, lambda value: progress(value * 20)) != manifest['source']['sha256']:
        raise ValueError('일본판 원본 ISO의 SHA-256이 다릅니다. README의 해시를 확인하십시오.')
    if shutil.disk_usage(destination.parent).free < manifest['target']['size'] + 64 * 1024 * 1024:
        raise ValueError('출력 폴더의 여유 공간이 부족합니다. 2GB 이상을 확보하십시오.')
    temporary = destination.parent / ('.' + destination.name + '.' + uuid.uuid4().hex + '.partial')
    file_count = len(manifest['files'])
    modified = sum(bool(item.get('delta')) for item in manifest['files'])
    try:
        with zipfile.ZipFile(bundle) as archive, source.open('rb') as original, temporary.open('xb') as output:
            output.truncate(manifest['target']['size'])
            for item in manifest['metadata']:
                output.seek(item['offset'])
                output.write(checked_member(archive, item['payload'], item['sha256']))
            with tempfile.TemporaryDirectory(prefix='.ffzero-v08-', dir=destination.parent) as work:
                work = Path(work)
                for index, item in enumerate(manifest['files']):
                    if item.get('delta'):
                        old = read_exact(original, item['source_offset'], item['source_size'])
                        if hashlib.sha256(old).hexdigest() != item['source_sha256']:
                            raise ValueError('원본 리소스 해시 불일치: ' + item['path'])
                        (work / 'old.bin').write_bytes(old)
                        (work / 'delta.vcdiff').write_bytes(checked_member(archive, item['delta'], item['delta_sha256']))
                        new = work / 'new.bin'
                        new.unlink(missing_ok=True)
                        result = subprocess.run(
                            [str(xdelta), '-d', '-D', '-R', '-s', str(work / 'old.bin'),
                             str(work / 'delta.vcdiff'), str(new)],
                            capture_output=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        if result.returncode:
                            raise RuntimeError('xdelta3 변환 실패: ' + item['path'] + '\n' +
                                               result.stderr.decode('utf-8', errors='replace')[-1500:])
                        if new.stat().st_size != item['size'] or digest(new) != item['sha256']:
                            raise ValueError('패치 결과 해시 불일치: ' + item['path'])
                        output.seek(item['offset'])
                        output.write(new.read_bytes())
                        log('한국어 반영: ' + item['path'])
                    else:
                        copy_range(original, output, item)
                    progress(20 + (index + 1) / file_count * 65)
        log('완성 ISO 전체 SHA-256을 대조합니다...')
        actual = digest(temporary, lambda value: progress(85 + value * 15))
        if actual != manifest['target']['sha256']:
            raise ValueError('완성 ISO의 전체 해시가 다릅니다.')
        # Windows rename refuses to replace an existing destination. The link
        # branch provides the same no-clobber behavior on POSIX filesystems.
        if os.name == 'nt':
            os.rename(temporary, destination)
        else:
            os.link(temporary, destination)
            temporary.unlink()
        report = dict(version=manifest['version'], source_sha256=manifest['source']['sha256'],
                      target_sha256=actual, size=destination.stat().st_size,
                      files=file_count, modified_files=modified,
                      original_modified=False, all_file_bytes_verified=True,
                      output=str(destination))
        log('완료: ' + str(destination))
        return report
    finally:
        temporary.unlink(missing_ok=True)
