"""Microphone samples timestamped against the same monotonic clock as the camera."""
from collections import deque
import threading
import time
import wave

import sounddevice as sd


def input_devices():
    hosts = sd.query_hostapis()
    devices = [(index, device) for index, device in enumerate(sd.query_devices())
               if device['max_input_channels'] > 0]
    wasapi = [(index, device) for index, device in devices
              if hosts[device['hostapi']]['name'] == 'Windows WASAPI']
    return [(index, device['name']) for index, device in (wasapi or devices)]


def input_rate(device):
    try:
        info = sd.query_devices(device, 'input')
        rate = int(info['default_samplerate'])
        sd.check_input_settings(device=device, channels=1, dtype='int16', samplerate=rate)
        return rate
    except Exception as exc:
        raise ValueError(f'No se puede usar el micrófono seleccionado: {exc}') from exc


class AudioBuffer:
    """A bounded RAM buffer; no microphone audio is saved outside a motion clip."""
    def __init__(self, rate):
        self.rate = rate
        self.blocks = deque(maxlen=512)
        self.condition = threading.Condition()
        self.error = None

    def append(self, timestamp, data):
        with self.condition:
            self.blocks.append((timestamp, data))
            # Keep at most ten seconds, even with large host-provided blocks.
            while len(self.blocks) > 1 and timestamp - self.blocks[0][0] > 10:
                self.blocks.popleft()
            self.condition.notify_all()

    def fail(self, message):
        with self.condition:
            self.error = message
            self.condition.notify_all()

    def read(self, start, offset, target, wait=False):
        """Return available mono PCM samples for [offset, target), relative to start."""
        deadline = time.monotonic() + 1.5 if wait else 0
        with self.condition:
            while True:
                if self.error:
                    raise RuntimeError(self.error)
                if self.blocks:
                    timestamp, data = self.blocks[-1]
                    available = round((timestamp - start) * self.rate) + len(data) // 2
                else:
                    available = 0
                if not wait or available >= target:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('El micrófono dejó de entregar audio. Revisá su conexión y los permisos de Windows.')
                self.condition.wait(remaining)
            blocks = tuple(self.blocks)
        end = min(target, available)
        if end <= offset:
            return b''
        result = bytearray((end - offset) * 2)
        covered = offset
        for timestamp, data in blocks:
            block_start = round((timestamp - start) * self.rate)
            left, right = max(offset, block_start), min(end, block_start + len(data) // 2)
            if right <= left:
                continue
            if left > covered + 1:
                raise RuntimeError('Se perdieron muestras de audio; no se puede garantizar la sincronización.')
            result[(left - offset) * 2:(right - offset) * 2] = data[(left - block_start) * 2:(right - block_start) * 2]
            covered = max(covered, right)
        if covered < end - 1:
            raise RuntimeError('No hay audio suficiente para completar el clip.')
        return bytes(result)


class MicrophoneInput:
    def __init__(self, device=None):
        self.rate = input_rate(device)
        self.buffer = AudioBuffer(self.rate)
        self.first_sample = None
        self.samples_received = 0
        self.stream = None
        try:
            self.stream = sd.RawInputStream(device=device, samplerate=self.rate, channels=1,
                                            dtype='int16', blocksize=0, latency='high', callback=self._callback)
            # PortAudio timestamps and the camera's monotonic clock have different origins.
            before = time.monotonic()
            stream_time = self.stream.time
            self.clock_offset = (before + time.monotonic()) / 2 - stream_time
            self.input_latency = self.stream.latency
            self.stream.start()
        except Exception as exc:
            self.close()
            raise RuntimeError(f'No se pudo abrir el micrófono. Revisá su conexión y el permiso de micrófono para aplicaciones de escritorio: {exc}') from exc

    def _callback(self, data, frames, timing, status):
        if status:
            self.buffer.fail(f'La captura de audio se interrumpió: {status}')
            raise sd.CallbackAbort
        # Some Windows MME drivers return zero for both callback timestamps.
        # Anchor those streams to callback arrival minus the reported latency.
        if timing.inputBufferAdcTime > 0 and timing.currentTime > 0:
            observed = self.clock_offset + timing.inputBufferAdcTime
        else:
            observed = time.monotonic() - self.input_latency
        if self.first_sample is None:
            self.first_sample = observed
        timestamp = self.first_sample + self.samples_received / self.rate
        if abs(observed - timestamp) > .25:
            self.buffer.fail('El reloj del micrófono cambió; se detuvo la grabación para evitar audio desincronizado.')
            raise sd.CallbackAbort
        self.buffer.append(timestamp, bytes(data))
        self.samples_received += frames

    def check(self):
        if self.buffer.error:
            raise RuntimeError(self.buffer.error)
        if self.stream is None or not self.stream.active:
            raise RuntimeError('El micrófono se desconectó o dejó de capturar audio.')

    def close(self):
        if self.stream is not None:
            stream, self.stream = self.stream, None
            stream.close()


class AudioClip:
    def __init__(self, microphone, path, started):
        self.microphone = microphone
        self.path = path
        self.started = started
        self.written = 0
        self.wav = wave.open(str(path), 'wb')
        self.wav.setnchannels(1)
        self.wav.setsampwidth(2)
        self.wav.setframerate(microphone.rate)

    def update(self, duration, final=False):
        self.microphone.check()
        target = round(duration * self.microphone.rate)
        data = self.microphone.buffer.read(self.started, self.written, target, wait=final)
        self.wav.writeframesraw(data)
        self.written += len(data) // 2

    def close(self):
        if self.wav is not None:
            wav, self.wav = self.wav, None
            wav.close()
