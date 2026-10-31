"""Build a single Windows executable, including the compiled media helper."""
from pathlib import Path
import shutil
import subprocess
import sys

from media import ensure_player


def main():
    root = Path(__file__).resolve().parent
    # Fail early instead of producing an executable without its GUI.
    import tkinter
    tkinter.Tcl()
    subprocess.run([sys.executable, '-m', 'unittest', '-q'], cwd=root, check=True)
    native = root / '.build' / 'package' / 'native'
    native.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ensure_player(), native / 'MediaPlayer.exe')
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--windowed', '--name', 'VigilanciaWebcam',
        '--add-data', f'{native / "MediaPlayer.exe"}:native',
        '--distpath', str(root / 'dist'),
        '--workpath', str(root / '.build' / 'pyinstaller'),
        '--specpath', str(root / '.build'),
        str(root / 'app.py'),
    ], cwd=root, check=True)
    print(root / 'dist' / 'VigilanciaWebcam.exe')


if __name__ == '__main__':
    main()
