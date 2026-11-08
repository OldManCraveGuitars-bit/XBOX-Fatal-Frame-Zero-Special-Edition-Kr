"""Release guards: source rejection, payload integrity and output preservation."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'patcher'))
from core import apply_patch, inspect_bundle, validate_manifest

CONFIG = json.loads((ROOT / 'patcher/release-config.json').read_text(encoding='utf-8'))
BUNDLE = ROOT / 'patches' / CONFIG['bundle']
XDELTA = ROOT / 'vendor/xdelta3/xdelta3.exe'


def test_public_delta_inventory_and_hashes():
    with zipfile.ZipFile(BUNDLE) as archive:
        data = json.loads(archive.read('manifest.json'))
        validate_manifest(data)
        assert len(data['files']) == 1928
        assert sum(bool(x.get('delta')) for x in data['files']) == 56
        assert data['target']['sha256'] == 'cf9520d7a245a637af0b3ee15234ba9a9c40930bddf937caded893568251599b'
        assert all(n.startswith(('metadata/', 'deltas/')) or n == 'manifest.json' for n in archive.namelist())
        assert not any(n.endswith(('.iso', '.xbe', '.msg', '.tex', '.dds', '.ccm')) for n in archive.namelist())
        for item in data['metadata']:
            assert hashlib.sha256(archive.read(item['payload'])).hexdigest() == item['sha256']
        for item in data['files']:
            if item.get('delta'):
                assert hashlib.sha256(archive.read(item['delta'])).hexdigest() == item['delta_sha256']
    assert hashlib.sha256(BUNDLE.read_bytes()).hexdigest() == CONFIG['bundle_sha256']


def test_modified_bundle_rejected(tmp_path):
    bad = tmp_path / 'bad.ffpatch'
    bad.write_bytes(BUNDLE.read_bytes() + b'tampered')
    with pytest.raises(ValueError, match='SHA-256'):
        inspect_bundle(bad, XDELTA, CONFIG['bundle_sha256'], CONFIG['xdelta_sha256'])


def test_modified_decoder_rejected(tmp_path):
    bad = tmp_path/'xdelta3.exe'
    bad.write_bytes(b'wrong decoder')
    with pytest.raises(ValueError, match='xdelta3'):
        inspect_bundle(BUNDLE, bad, CONFIG['bundle_sha256'], CONFIG['xdelta_sha256'])


def test_failed_final_hash_cleans_partial_without_touching_source(tmp_path):
    source, target = tmp_path/'original.iso', tmp_path/'output.iso'
    source.write_bytes(b'abc')
    item = dict(offset=0, size=3, payload='metadata/0000.bin',
                sha256=hashlib.sha256(b'abc').hexdigest())
    manifest = dict(format='ffzero-xiso-vcdiff-1', version='test',
                    source=dict(size=3, sha256=item['sha256']),
                    target=dict(size=3, sha256='0'*64), files=[], metadata=[item])
    bundle = tmp_path/'failure.ffpatch'
    with zipfile.ZipFile(bundle, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr(item['payload'], b'abc')
    with pytest.raises(ValueError, match='전체 해시'):
        apply_patch(source, target, bundle, XDELTA, hashlib.sha256(bundle.read_bytes()).hexdigest(), CONFIG['xdelta_sha256'])
    assert source.read_bytes() == b'abc'
    assert not target.exists()
    assert not list(tmp_path.glob('*.partial'))


def test_existing_output_is_preserved(tmp_path):
    source, target = tmp_path / 'source.iso', tmp_path / 'target.iso'
    source.write_bytes(b'original')
    target.write_bytes(b'existing output')
    with pytest.raises(FileExistsError):
        apply_patch(source, target, BUNDLE, XDELTA, CONFIG['bundle_sha256'], CONFIG['xdelta_sha256'])
    assert source.read_bytes() == b'original'
    assert target.read_bytes() == b'existing output'


def test_same_source_output_rejected(tmp_path):
    source = tmp_path / 'source.iso'
    source.write_bytes(b'original')
    with pytest.raises(ValueError, match='다른 출력'):
        apply_patch(source, source, BUNDLE, XDELTA, CONFIG['bundle_sha256'], CONFIG['xdelta_sha256'])
    assert source.read_bytes() == b'original'


@pytest.mark.skipif(not XDELTA.is_file(), reason='Local vendor binary required')
def test_wrong_size_source_creates_no_output(tmp_path):
    source, target = tmp_path / 'source.iso', tmp_path / 'target.iso'
    source.write_bytes(b'wrong ISO')
    with pytest.raises(ValueError, match='크기'):
        apply_patch(source, target, BUNDLE, XDELTA, CONFIG['bundle_sha256'], CONFIG['xdelta_sha256'])
    assert not target.exists()
    assert not list(tmp_path.glob('*.partial'))


def test_overlapping_metadata_rejected():
    with zipfile.ZipFile(BUNDLE) as archive:
        data = json.loads(archive.read('manifest.json'))
    data['metadata'].append(data['metadata'][0].copy())
    with pytest.raises(ValueError, match='겹칩니다'):
        validate_manifest(data)


@pytest.mark.skipif(not XDELTA.is_file(), reason='Local vendor binary required')
def test_wrong_same_size_source_rejected_before_write(tmp_path):
    """Use a tiny synthetic manifest to exercise the full-size hash gate."""
    source, target = tmp_path / 'source.iso', tmp_path / 'target.iso'
    source.write_bytes(b'not-the-source')
    manifest = dict(format='ffzero-xiso-vcdiff-1', version='test',
                    source=dict(size=source.stat().st_size, sha256='0' * 64),
                    target=dict(size=1, sha256='0' * 64), files=[], metadata=[])
    bundle = tmp_path / 'gate.ffpatch'
    with zipfile.ZipFile(bundle, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
    with pytest.raises(ValueError, match='원본 ISO의 SHA-256'):
        apply_patch(source, target, bundle, XDELTA, hashlib.sha256(bundle.read_bytes()).hexdigest(), CONFIG['xdelta_sha256'])
    assert not target.exists()
    assert source.read_bytes() == b'not-the-source'
