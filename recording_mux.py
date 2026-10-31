"""Join local video/audio files in the background; never launch shell commands."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys


def ffmpeg_executable():
    if getattr(sys, 'frozen', False):
        executable = Path(sys._MEIPASS) / 'native' / 'ffmpeg.exe'
    else:
        import imageio_ffmpeg
        executable = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not executable.is_file():
        raise RuntimeError('No se encontró el componente para guardar el audio del video.')
    return str(executable)


def mux_clip(video, audio, duration, report):
    destination = video.with_name(video.name.replace('.grabando.avi', '.avi'))
    pending = video.with_name(video.name.replace('.grabando.avi', '.uniendo.avi'))
    try:
        command = [ffmpeg_executable(), '-nostdin', '-hide_banner', '-loglevel', 'error', '-n',
                   '-i', str(video), '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
                   '-c:v', 'copy', '-c:a', 'pcm_s16le', '-t', f'{duration:.6f}', str(pending)]
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip()[-700:])
        if not pending.is_file() or pending.stat().st_size == 0:
            raise RuntimeError('El archivo combinado está vacío.')
        pending.rename(destination)
    except Exception as exc:
        report('save_error', video, f'No se pudo guardar el clip con audio: {exc}. Se conservan los archivos de video y audio en {video.parent}.')
        return
    # These are this clip's own intermediate files; never remove unrelated files.
    for path in (video, audio):
        try:
            path.unlink()
        except OSError:
            pass
    report('saved', destination, 'Clip con audio guardado')


class ClipFinalizer:
    def __init__(self, report):
        self.report = report
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='guardar-clip')
        self.pending = []

    def submit(self, video, audio, duration):
        self.pending = [job for job in self.pending if not job.done()]
        if len(self.pending) >= 2:
            raise RuntimeError('El disco no alcanza a guardar los clips con audio. Se conservan los archivos parciales.')
        self.report('processing', video, 'Guardando clip con audio')
        self.pending.append(self.executor.submit(mux_clip, video, audio, duration, self.report))

    def close(self):
        self.executor.shutdown(wait=True)
