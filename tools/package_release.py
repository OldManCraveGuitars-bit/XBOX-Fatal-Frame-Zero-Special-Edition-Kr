"""Publishable files only: standalone EXE, usage, licenses and checksums."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STEM = 'XBOX-Fatal-Frame-Zero-Special-Edition-Kr-V0.8'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    config = json.loads((ROOT/'patcher/release-config.json').read_text(encoding='utf-8'))
    check = json.loads((ROOT/'build/exe-roundtrip.json').read_text(encoding='utf-8'))
    ui = json.loads((ROOT/'build/exe-ui-smoke.json').read_text(encoding='utf-8'))
    assert check['version'] == 'V0.8' and check['target_sha256'] == config['target']['sha256']
    assert check['files'] == 1928 and check['modified_files'] == 56
    assert check['all_file_bytes_verified'] and not check['original_modified']
    assert ui['gui_widgets_visible'] and ui['patch_button_inside_window']
    exe = ROOT/'release'/(STEM+'-Patcher.exe')
    readme = ('령 스페셜 에디션 Xbox 일본판 한국어 패치 V0.8\n'
              '코리아 로컬라이즈 GiKakNo\n\n'
              f'1. {exe.name}를 실행합니다.\n'
              '2. 패치하지 않은 일본판 원본 ISO를 선택합니다.\n'
              '3. 새 ISO의 저장 경로를 고르고 한국어 ISO 만들기를 누릅니다.\n'
              '4. 완료와 전체 해시 검사 통과를 확인합니다.\n\n'
              'Windows 64비트용. Python 설치 불필요. 출력 폴더 여유 공간 2GB 이상.\n'
              '차분은 EXE에 내장되어 있습니다. 원본과 기존 출력 파일은 덮어쓰지 않습니다.\n\n'
              f"원본: {config['source']['size']:,}바이트\nSHA-256: {config['source']['sha256']}\n\n"
              f"결과: {config['target']['size']:,}바이트\nSHA-256: {config['target']['sha256']}\n\n"
              '실기 화면·전편 진행·음성/자막 동기의 최종 확인이 남은 공개 시험판입니다.\n'
              '게임 ISO·원본 게임 파일·제작용 분석 자료는 포함하지 않습니다.\n\n'
              '설명·화면 미리보기·오류 제보:\n'
              'https://github.com/OldManCraveGuitars-bit/XBOX-Fatal-Frame-Zero-Special-Edition-Kr\n')
    archive_path = ROOT/'release'/(STEM+'-Windows-Patcher.zip')
    files = [(exe, exe.name)] + [(p, p.relative_to(ROOT).as_posix()) for p in sorted((ROOT/'licenses').iterdir()) if p.is_file()]
    sums = []
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in files:
            archive.write(path, name)
            sums.append(sha(path)+'  '+name)
        usage = readme.encode('utf-8-sig')
        archive.writestr('사용법.txt', usage)
        sums.append(hashlib.sha256(usage).hexdigest()+'  사용법.txt')
        archive.writestr('SHA256SUMS.txt', '\n'.join(sums)+'\n')
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files)+2
        assert not any(name.lower().endswith(('.iso', '.xiso', '.xbe', '.wmv', '.obj', '.xp2', '.pkz', '.ffpatch')) for name in archive.namelist())
        for entry in sums:
            expected, name = entry.split('  ', 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
    checksum = sha(archive_path)
    (ROOT/'release/SHA256SUMS.txt').write_text(checksum+'  '+archive_path.name+'\n', encoding='utf-8')
    result = dict(version='V0.8', download=archive_path.name, size=archive_path.stat().st_size,
                  sha256=checksum, exe=dict(name=exe.name, size=exe.stat().st_size, sha256=sha(exe)),
                  source=config['source'], target=config['target'], original_game_files_included=False,
                  package_entries=[n for _, n in files]+['사용법.txt', 'SHA256SUMS.txt'])
    (ROOT/'release-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
