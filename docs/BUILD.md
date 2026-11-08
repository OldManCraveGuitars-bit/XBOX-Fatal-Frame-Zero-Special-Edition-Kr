# EXE 패처 빌드

Windows 64비트와 Python 3.13을 기준으로 합니다.

```powershell
python -m pip install -r requirements-build.txt
```

차분 생성에는 README의 해시와 일치하는 원본 ISO 및 검증된 V0.8 결과 ISO가 필요합니다.
이 두 ISO는 저장소나 릴리스에 포함하지 않습니다.

```powershell
python tools/build_public_patch.py --source "D:\Games\Fatal Frame - Zero Special Edition (Japan).iso" --target "D:\Games\Fatal-Frame-Zero-Special-Edition-Kr-V0.8.xiso.iso" --xdelta vendor/xdelta3/xdelta3.exe --output patches/Fatal-Frame-Zero-Special-Edition-Kr-V0.8.ffpatch
```

생성한 차분과 xdelta 실행 파일의 SHA-256은 `patcher/release-config.json`과 일치해야 합니다.
차분은 변경된 게임 파일 56개의 VCDIFF와 새 XDVDFS 디렉터리 정보만 담고, 변경 없는 파일은 사용자의 원본 ISO에서 복사합니다.
동일한 원본과 결과로도 xdelta 버전/빌드가 다르면 차분 바이트가 달라질 수 있습니다. 설정 해시는 의도적으로 묶여 있습니다.

```powershell
python -m pytest tests -q
python tools/build_windows_release.py
```

`release/`에 EXE가 생성됩니다. 소스 실행도 가능합니다.

```powershell
python patcher/app.py --inspect --report inspect.json
python patcher/app.py --source "D:\Games\original.iso" --output "D:\Games\Korean.iso" --report patch-result.json
```

EXE도 같은 명령행 옵션을 지원합니다. 파일 경로에 공백이 있으면 따옴표로 감싸십시오.
기존 출력 파일은 덮어쓰지 않으며, 결과 해시가 다르면 임시 출력만 제거합니다.

저장소의 `patches/`, `build/`, `release/` 산출물은 Git에서 제외합니다.
한국어 번역·텍스처를 새로 편집하는 전체 제작 프로젝트는 이 최소 배포용 패처 저장소와 별도입니다.
