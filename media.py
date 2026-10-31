"""Owned Windows media processes: local files only, no command interpolation."""
import os
import hashlib
from pathlib import Path
import subprocess
import sys


def ensure_player():
    if os.name != 'nt':
        raise RuntimeError('La reproducción de esta versión requiere Windows.')
    if getattr(sys, 'frozen', False):
        player = Path(sys._MEIPASS) / 'native' / 'MediaPlayer.exe'
        if not player.is_file():
            raise RuntimeError('El ejecutable no contiene el reproductor multimedia.')
        return player
    source = Path(__file__).with_name('MediaPlayer.cs')
    placement = source.with_name('WindowPlacement.cs')
    video = source.with_name('VlcVideo.cs')
    manifest = source.with_suffix('.manifest')
    output_dir = source.parent / '.build'
    version = hashlib.sha256(source.read_bytes() + placement.read_bytes() + video.read_bytes() + manifest.read_bytes()).hexdigest()[:12]
    player = output_dir / f'MediaPlayer_{version}.exe'
    if player.is_file():
        return player
    framework = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319'
    if not (framework / 'csc.exe').is_file():
        framework = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework/v4.0.30319'
    if not (framework / 'csc.exe').is_file():
        raise RuntimeError('No se encontró .NET Framework de Windows para preparar el reproductor.')
    output_dir.mkdir(exist_ok=True)
    command = [str(framework / 'csc.exe'), '/nologo', '/utf8output', '/target:exe', f'/out:{player}', f'/win32manifest:{manifest}']
    for library in ('PresentationFramework', 'PresentationCore', 'WindowsBase'):
        command.append(f'/reference:{framework / "WPF" / (library + ".dll")}')
    command.append(f'/reference:{framework / "System.Xaml.dll"}')
    command.append(f'/reference:{framework / "System.Windows.Forms.dll"}')
    command.append(f'/reference:{framework / "System.Drawing.dll"}')
    command.append(f'/reference:{framework / "WPF" / "WindowsFormsIntegration.dll"}')
    command.append(str(video))
    command.append(str(placement))
    command.append(str(source))
    result = subprocess.run(command, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        error = (result.stdout + result.stderr).decode('utf-8', errors='replace')
        raise RuntimeError(f'No se pudo preparar el reproductor: {error}')
    return player


class MediaHandle:
    def __init__(self, process):
        self.process = process
        self.error = ''
        self.collected = False

    def poll(self):
        code = self.process.poll()
        if code is not None and not self.collected:
            _, error = self.process.communicate()
            self.error = (error or b'').decode('utf-8', errors='replace').strip()[-1000:]
            self.collected = True
        return code

    def stop(self):
        if self.collected:
            return
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate(timeout=2)
        self.collected = True


def launch_media(action):
    if os.name != 'nt':
        raise RuntimeError('La reproducción de esta versión requiere Windows.')
    path = Path(action.path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('El archivo seleccionado no existe.')
    if str(path).startswith('\\\\'):
        raise ValueError('Elegí un archivo guardado en esta PC.')
    player = ensure_player()
    command = [
        str(player), action.kind, str(path), str(action.duration), str(os.getpid()),
        str(action.loop).lower(), str(action.keep_open).lower(),
        action.monitor, str(action.fullscreen).lower(),
    ]
    return MediaHandle(subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW,
    ))
