"""Freeze only the standalone, source-checked V0.8 patcher."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = 'XBOX-Fatal-Frame-Zero-Special-Edition-Kr-V0.8-Patcher'


def main():
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onefile', '--windowed', '--name', NAME,
        '--distpath', str(ROOT/'release'), '--workpath', str(ROOT/'build/pyinstaller'),
        '--specpath', str(ROOT/'build'), '--paths', str(ROOT/'patcher'),
        '--add-data', str(ROOT/'patcher/release-config.json')+';release',
        '--add-data', str(ROOT/'patches/Fatal-Frame-Zero-Special-Edition-Kr-V0.8.ffpatch')+';release',
        '--add-data', str(ROOT/'docs/images/title.png')+';release',
        '--add-binary', str(ROOT/'vendor/xdelta3/xdelta3.exe')+';release',
        str(ROOT/'patcher/app.py')], check=True)


if __name__ == '__main__':
    main()
