"""Motion clips owned by the camera thread, independent of action repetition."""
from dataclasses import dataclass
from datetime import datetime
import math
import os
from pathlib import Path
import shutil
import tempfile

import cv2
from microphone import AudioClip, MicrophoneInput, input_rate
from recording_mux import ClipFinalizer, ffmpeg_executable


@dataclass(frozen=True)
class RecordingConfig:
    folder: Path
    quiet_seconds: float = 5
    audio: bool = True
    microphone: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'folder', Path(self.folder).expanduser().resolve())
        if not math.isfinite(self.quiet_seconds) or not 1 <= self.quiet_seconds <= 60:
            raise ValueError('El tiempo sin movimiento debe estar entre 1 y 60 segundos.')
        if not isinstance(self.audio, bool) or (self.microphone is not None and
                (type(self.microphone) is not int or self.microphone < 0)):
            raise ValueError('La configuración del micrófono no es válida.')

    def prepare(self):
        """Check the chosen destination before arming, including write permissions."""
        if self.audio:
            input_rate(self.microphone)
            ffmpeg_executable()
        self.folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=self.folder) as probe:
            probe.write(b'webcam')
            probe.flush()


class MotionRecorder:
    FPS = 10
    MAX_SECONDS = 300
    MIN_FREE_BYTES = 100 * 1024 * 1024
    MAX_FRAME_GAP = 2

    def __init__(self, config, report):
        self.config = config
        self.report = report  # (kind, path, message), dispatched to the UI by a queue
        self.writer = None
        self.path = None
        self.failed = False
        self.last_frame = None
        self.last_space_check = float('-inf')
        self.microphone = None
        self.audio_clip = None
        self.finalizer = None
        if config.audio:
            try:
                self.microphone = MicrophoneInput(config.microphone)
                self.finalizer = ClipFinalizer(report)
            except Exception as exc:
                self._fail(exc)

    def update(self, frame, now, moving, confirmed):
        if self.failed:
            return
        try:
            if self.microphone is not None:
                self.microphone.check()
            # A suspended/disconnected camera must not fabricate minutes of footage.
            if self.writer is not None and now - self.last_sample > self.MAX_FRAME_GAP:
                self._finish()
            if self.writer is not None and moving:
                self.last_motion = now
            if self.writer is not None and now >= self.last_motion + self.config.quiet_seconds:
                self._write_until(self.last_motion + self.config.quiet_seconds, self.last_frame, endpoint=False)
                self._finish()
            if self.writer is not None and now >= self.started + self.MAX_SECONDS:
                self._write_until(self.started + self.MAX_SECONDS, self.last_frame, endpoint=False)
                last_motion = self.last_motion
                self._finish()
                self._start(frame, now)
                self.last_motion = last_motion
            if self.writer is None and confirmed:
                self._start(frame, now)
            if self.writer is not None:
                if now - self.last_space_check >= 1:
                    self._check_space()
                    self.last_space_check = now
                self._write_until(now, frame)
                if self.audio_clip is not None:
                    self.audio_clip.update(self.frames_written / self.FPS)
                self.last_sample = now
                self.last_frame = frame.copy()
        except Exception as exc:
            self._fail(exc)

    def _check_space(self):
        if shutil.disk_usage(self.config.folder).free < self.MIN_FREE_BYTES:
            raise OSError('Quedan menos de 100 MB libres en el disco de grabación.')

    def _start(self, frame, now):
        self._check_space()
        prefix = 'movimiento_' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '_'
        descriptor, name = tempfile.mkstemp(prefix=prefix, suffix='.grabando.avi', dir=self.config.folder)
        os.close(descriptor)
        self.path = Path(name)
        height, width = frame.shape[:2]
        self.writer = cv2.VideoWriter(str(self.path), cv2.CAP_FFMPEG,
                                      cv2.VideoWriter_fourcc(*'MJPG'), self.FPS, (width, height))
        if not self.writer.isOpened():
            raise RuntimeError('No se pudo crear el video. Revisá la carpeta y el espacio disponible.')
        self.started = self.last_motion = self.last_sample = now
        self.frames_written = 0
        self.last_frame = frame.copy()
        self.last_space_check = now
        if self.microphone is not None:
            audio_path = self.path.with_suffix('.wav')
            self.audio_clip = AudioClip(self.microphone, audio_path, now)
        self.report('started', self.path, 'Grabando movimiento con audio' if self.config.audio else 'Grabando movimiento sin audio')

    def _write_until(self, now, frame, endpoint=True):
        # AVI uses a fixed frame rate. Resample by elapsed time so slower/faster
        # camera capture does not make the saved clip play at the wrong speed.
        elapsed_frames = max(0, now - self.started) * self.FPS
        target = (math.floor(elapsed_frames + 1e-7) + 1 if endpoint
                  else math.ceil(elapsed_frames - 1e-7))
        target = min(target, int(self.MAX_SECONDS * self.FPS))
        while self.frames_written < target:
            sample = frame if self.frames_written == target - 1 else self.last_frame
            self.writer.write(sample)
            self.frames_written += 1

    def _finish(self):
        if self.writer is None:
            return
        writer, self.writer = self.writer, None
        writer.release()
        # Do not announce an unreadable/empty clip as successfully saved.
        reader = cv2.VideoCapture(str(self.path))
        try:
            ok, _ = reader.read()
            if not ok:
                raise OSError('El archivo grabado no se pudo verificar.')
        finally:
            reader.release()
        if self.audio_clip is not None:
            self.audio_clip.update(self.frames_written / self.FPS, final=True)
            self.audio_clip.close()
            self.finalizer.submit(self.path, self.audio_clip.path, self.frames_written / self.FPS)
            self.audio_clip = None
        else:
            destination = self.path.with_name(self.path.name.replace('.grabando.avi', '.avi'))
            self.path.rename(destination)
            self.report('saved', destination, 'Clip sin audio guardado')
        self.path = None
        self.last_frame = None

    def _fail(self, exc):
        self.failed = True
        if self.audio_clip is not None:
            try:
                self.audio_clip.close()
            except Exception:
                pass
            self.audio_clip = None
        if self.microphone is not None:
            try:
                self.microphone.close()
            except Exception:
                pass
            self.microphone = None
        if self.writer is not None:
            writer, self.writer = self.writer, None
            try:
                writer.release()
            except Exception:
                pass
        path, self.path = self.path, None
        self.last_frame = None
        message = f'Grabación detenida: {exc} La detección continúa. Detené y reactivá la vigilancia para reintentar.'
        if path is not None:
            message += f' Archivo parcial: {path}'
        self.report('error', path, message)

    def close(self):
        try:
            self._finish()
        except Exception as exc:
            self._fail(exc)
        finally:
            if self.microphone is not None:
                self.microphone.close()
                self.microphone = None
            if self.finalizer is not None:
                self.finalizer.close()
                self.finalizer = None
