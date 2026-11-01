from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

import cv2
import numpy as np
import sounddevice as sd

from app import Monitor
from microphone import AudioBuffer, AudioClip, MicrophoneInput
from recording import MotionRecorder, RecordingConfig
from recording_mux import ffmpeg_executable, mux_clip


class AudioTimelineTests(unittest.TestCase):
    def test_selects_only_the_clip_interval_across_audio_blocks(self):
        buffer = AudioBuffer(1000)
        buffer.append(10, np.arange(100, dtype=np.int16).tobytes())
        buffer.append(10.1, np.arange(100, 200, dtype=np.int16).tobytes())
        actual = np.frombuffer(buffer.read(10.05, 0, 100), dtype=np.int16)
        np.testing.assert_array_equal(actual, np.arange(50, 150))

    def test_live_read_waits_for_samples_instead_of_inventing_silence(self):
        buffer = AudioBuffer(1000)
        buffer.append(10, b'\x01\0' * 100)
        self.assertEqual(len(buffer.read(10, 0, 150)), 200)
        self.assertEqual(buffer.read(10, 100, 150), b'')
        buffer.append(10.1, b'\x02\0' * 100)
        self.assertEqual(buffer.read(10, 100, 150), b'\x02\0' * 50)

    def test_lost_audio_is_reported(self):
        buffer = AudioBuffer(1000)
        buffer.append(10, b'\0' * 200)
        buffer.append(10.2, b'\0' * 200)
        with self.assertRaisesRegex(RuntimeError, 'perdieron muestras'):
            buffer.read(10, 0, 300)
        buffer.fail('micrófono desconectado')
        with self.assertRaisesRegex(RuntimeError, 'desconectado'):
            buffer.read(10, 0, 300)

    def test_audio_before_the_clip_is_bounded_in_memory(self):
        buffer = AudioBuffer(1000)
        for index in range(100):
            buffer.append(index, b'\0' * 2000)
        self.assertLessEqual(len(buffer.blocks), 11)
        with self.assertRaises(RuntimeError):
            buffer.read(0, 0, 100)

    def test_callback_clock_offset_and_overflow_propagation(self):
        microphone = MicrophoneInput.__new__(MicrophoneInput)
        microphone.rate = 1000
        microphone.buffer = AudioBuffer(1000)
        microphone.first_sample = None
        microphone.samples_received = 0
        microphone.clock_offset = 90
        microphone._callback(b'\x01\0' * 100, 100, Mock(inputBufferAdcTime=10, currentTime=10.1), False)
        microphone._callback(b'\x02\0' * 100, 100, Mock(inputBufferAdcTime=10.1, currentTime=10.2), False)
        self.assertEqual(microphone.buffer.read(100, 0, 200), b'\x01\0' * 100 + b'\x02\0' * 100)
        with self.assertRaises(sd.CallbackAbort):
            microphone._callback(b'', 0, Mock(), 'input overflow')
        with self.assertRaises(RuntimeError):
            microphone.buffer.read(100, 0, 200)

    def test_legacy_driver_with_zero_timestamps_uses_reported_latency(self):
        microphone = MicrophoneInput.__new__(MicrophoneInput)
        microphone.rate = 1000
        microphone.buffer = AudioBuffer(1000)
        microphone.first_sample = None
        microphone.samples_received = 0
        microphone.input_latency = .1
        with patch('microphone.time.monotonic', side_effect=[100.1, 100.2]):
            microphone._callback(b'\x01\0' * 100, 100, Mock(inputBufferAdcTime=0, currentTime=0), False)
            microphone._callback(b'\x02\0' * 100, 100, Mock(inputBufferAdcTime=0, currentTime=0), False)
        self.assertEqual(microphone.buffer.read(100, 0, 200), b'\x01\0' * 100 + b'\x02\0' * 100)

    def test_clock_jump_stops_only_audio_and_reports_measured_drift(self):
        microphone = MicrophoneInput.__new__(MicrophoneInput)
        microphone.rate = 1000
        microphone.buffer = AudioBuffer(1000)
        microphone.first_sample = None
        microphone.samples_received = 0
        microphone.clock_offset = 90
        microphone._callback(b'\0' * 200, 100, Mock(inputBufferAdcTime=10, currentTime=10.1), False)
        with self.assertRaises(sd.CallbackAbort):
            microphone._callback(b'\0' * 200, 100, Mock(inputBufferAdcTime=10.5, currentTime=10.6), False)
        self.assertIn('400 ms', microphone.buffer.error)
        self.assertNotIn('se detuvo la grabación', microphone.buffer.error)


class RecordingAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.reports = []
        self.mic = Mock()
        self.mic.rate = 8000
        self.mic.buffer = AudioBuffer(8000)
        # A synthetic tone starts at t=.3, matching a visual change at frame 3.
        times = np.arange(24000) / 8000 - 1
        tone = np.where(times >= .3, np.sin(2 * np.pi * 440 * times) * 12000, 0).astype(np.int16)
        self.mic.buffer.append(-1, tone.tobytes())

    def recorder(self):
        with patch('recording.MicrophoneInput', return_value=self.mic):
            recorder = MotionRecorder(RecordingConfig(self.folder, 1), lambda *args: self.reports.append(args))
        self.addCleanup(recorder.close)
        return recorder

    def test_real_avi_contains_synced_audio_and_video_and_no_intermediates(self):
        recorder = self.recorder()
        for index in range(11):
            frame = np.full((48, 64, 3), 255 if index >= 3 else 0, np.uint8)
            recorder.update(frame, index / 10, index == 0, index == 0)
        recorder.close()
        self.assertEqual([r[0] for r in self.reports], ['started', 'processing', 'saved'])
        path = self.reports[-1][1]
        self.assertEqual(list(self.folder.iterdir()), [path])
        reader = cv2.VideoCapture(str(path))
        frames = []
        try:
            self.assertEqual(reader.get(cv2.CAP_PROP_FPS), 10)
            while True:
                ok, frame = reader.read()
                if not ok:
                    break
                frames.append(frame.mean())
        finally:
            reader.release()
        self.assertEqual(len(frames), 10)
        self.assertLess(frames[2], 5)
        self.assertGreater(frames[3], 250)
        result = subprocess.run([ffmpeg_executable(), '-v', 'error', '-nostdin', '-i', str(path),
                                 '-map', '0:a:0', '-f', 's16le', '-acodec', 'pcm_s16le', '-'],
                                capture_output=True, check=True, timeout=10,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        audio = np.frombuffer(result.stdout, dtype=np.int16)
        self.assertEqual(len(audio), 8000)
        self.assertTrue(np.all(audio[:2400] == 0))
        self.assertGreater(np.max(np.abs(audio[2400:])), 11000)
        self.mic.close.assert_called_once()

    def test_stopping_without_motion_releases_the_microphone_and_saves_nothing(self):
        recorder = self.recorder()
        recorder.update(np.zeros((48, 64, 3), np.uint8), 0, False, False)
        recorder.close()
        self.assertEqual(list(self.folder.iterdir()), [])
        self.mic.close.assert_called_once()

    def assert_silent_video(self, path, expected_frames):
        reader = cv2.VideoCapture(str(path))
        frames = []
        try:
            while True:
                ok, frame = reader.read()
                if not ok:
                    break
                frames.append(frame.mean())
        finally:
            reader.release()
        self.assertEqual(len(frames), expected_frames)
        result = subprocess.run([ffmpeg_executable(), '-v', 'error', '-nostdin', '-i', str(path),
                                 '-map', '0:a:0', '-f', 'null', '-'], capture_output=True, timeout=10,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'matches no streams', result.stderr)
        return frames

    def test_microphone_open_failure_warns_and_still_records_video(self):
        with patch('recording.MicrophoneInput', side_effect=RuntimeError('Acceso denegado')):
            recorder = MotionRecorder(RecordingConfig(self.folder), lambda *args: self.reports.append(args))
        recorder.update(np.zeros((48, 64, 3), np.uint8), 0, True, True)
        recorder.close()
        self.assertFalse(recorder.failed)
        self.assertEqual([r[0] for r in self.reports], ['audio_warning', 'started', 'saved'])
        self.assertIn('sin audio', self.reports[1][2])
        self.assert_silent_video(self.reports[-1][1], 1)

    def test_disconnect_keeps_all_video_and_future_clips_without_audio(self):
        recorder = self.recorder()
        frame = np.zeros((48, 64, 3), np.uint8)
        recorder.update(frame, 0, True, True)
        writer = recorder.writer
        self.mic.check.side_effect = RuntimeError('Micrófono desconectado')
        recorder.update(frame + 255, .1, True, True)
        self.assertIs(recorder.writer, writer)
        recorder.update(frame + 255, 1.1, False, False)
        recorder.update(frame, 2, True, True)
        recorder.close()
        self.assertFalse(recorder.failed)
        self.assertTrue(recorder.config.audio)  # Runtime fallback must not change the profile.
        self.assertEqual([r[0] for r in self.reports], ['started', 'audio_warning', 'saved', 'started', 'saved'])
        saved = [r[1] for r in self.reports if r[0] == 'saved']
        frames = self.assert_silent_video(saved[0], 11)
        self.assertLess(frames[0], 5)
        self.assertTrue(all(value > 250 for value in frames[1:]))
        self.assert_silent_video(saved[1], 1)
        self.assertEqual(set(self.folder.iterdir()), set(saved))
        self.mic.close.assert_called_once()

    def test_clock_failure_while_waiting_does_not_block_later_motion(self):
        recorder = self.recorder()
        self.mic.check.side_effect = RuntimeError('El reloj del micrófono se desvió 400 ms')
        frame = np.zeros((48, 64, 3), np.uint8)
        recorder.update(frame, 0, False, False)
        recorder.update(frame, .5, False, False)
        self.assertEqual(list(self.folder.iterdir()), [])
        recorder.update(frame, 10, True, True)
        recorder.close()
        self.assertFalse(recorder.failed)
        self.assertEqual([r[0] for r in self.reports], ['audio_warning', 'started', 'saved'])
        self.assert_silent_video(self.reports[-1][1], 1)

    def test_lost_samples_during_clip_fall_back_without_losing_frames(self):
        recorder = self.recorder()
        frame = np.zeros((48, 64, 3), np.uint8)
        recorder.update(frame, 0, True, True)
        self.mic.buffer.blocks.clear()
        self.mic.buffer.append(.3, b'\0' * 8000)
        recorder.update(frame, .4, True, True)
        recorder.close()
        self.assertFalse(recorder.failed)
        self.assertEqual([r[0] for r in self.reports], ['started', 'audio_warning', 'saved'])
        self.assertIn('perdieron muestras', self.reports[1][2])
        self.assert_silent_video(self.reports[-1][1], 5)

    def test_missing_audio_at_finalization_still_saves_complete_video(self):
        recorder = self.recorder()
        frame = np.zeros((48, 64, 3), np.uint8)
        recorder.update(frame, 0, True, True)
        recorder.update(frame, .3, True, True)
        with patch.object(self.mic.buffer, 'read', side_effect=RuntimeError('El micrófono dejó de entregar audio')):
            recorder.close()
        self.assertFalse(recorder.failed)
        self.assertEqual([r[0] for r in self.reports], ['started', 'audio_warning', 'saved'])
        self.assert_silent_video(self.reports[-1][1], 4)
        self.assertEqual(list(self.folder.iterdir()), [self.reports[-1][1]])

    def test_audio_fallback_still_splits_long_video_clips(self):
        recorder = self.recorder()
        recorder.MAX_SECONDS = 1
        frame = np.zeros((48, 64, 3), np.uint8)
        recorder.update(frame, 0, True, True)
        self.mic.check.side_effect = RuntimeError('Reloj desincronizado')
        for now in (.4, .8, 1, 1.4):
            recorder.update(frame, now, True, True)
        recorder.close()
        saved = [r[1] for r in self.reports if r[0] == 'saved']
        self.assertEqual(len(saved), 2)
        self.assert_silent_video(saved[0], 10)
        self.assert_silent_video(saved[1], 5)
        self.assertEqual([r[0] for r in self.reports].count('audio_warning'), 1)

    def test_audio_queue_full_saves_current_video_without_audio(self):
        recorder = self.recorder()
        recorder.update(np.zeros((48, 64, 3), np.uint8), 0, True, True)
        with patch.object(recorder.finalizer, 'submit', side_effect=RuntimeError('Cola llena')):
            recorder.close()
        self.assertFalse(recorder.failed)
        self.assertEqual([r[0] for r in self.reports], ['started', 'audio_warning', 'saved'])
        self.assert_silent_video(self.reports[-1][1], 1)

    def test_audio_cleanup_error_does_not_stop_video(self):
        recorder = self.recorder()
        frame = np.zeros((48, 64, 3), np.uint8)
        recorder.update(frame, 0, True, True)
        self.mic.check.side_effect = RuntimeError('Desconectado')
        self.mic.close.side_effect = RuntimeError('No responde')
        recorder.update(frame, .1, True, True)
        recorder.close()
        self.assertFalse(recorder.failed)
        self.assertIn('No se pudo cerrar el micrófono', self.reports[1][2])
        self.assert_silent_video(self.reports[-1][1], 2)

    def test_mux_failure_keeps_source_video_and_audio(self):
        video, audio = self.folder / 'movimiento_test.grabando.avi', self.folder / 'movimiento_test.grabando.wav'
        video.write_bytes(b'video')
        audio.write_bytes(b'audio')
        with patch('recording_mux.subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 30)):
            mux_clip(video, audio, 1, lambda *args: self.reports.append(args))
        self.assertEqual([r[0] for r in self.reports], ['save_error'])
        self.assertTrue(video.exists() and audio.exists())


class RecordingStatusTests(unittest.TestCase):
    def make_monitor(self):
        monitor = Monitor.__new__(Monitor)
        monitor.append_log = Mock()
        monitor.generation = 1
        monitor.armed = Mock()
        monitor.armed.get.return_value = True
        monitor.recording_status = Mock()
        monitor.recording_label = Mock()
        monitor.recording_active_path = None
        monitor.recording_failed = False
        monitor.recording_audio_disabled = False
        return monitor

    def test_background_save_does_not_hide_the_next_active_recording(self):
        monitor = self.make_monitor()
        first = Path('movimiento_1.grabando.avi')
        second = Path('movimiento_2.grabando.avi')
        monitor.handle_recording(('recording', 1, 'started', first, 'Grabando con audio'))
        monitor.handle_recording(('recording', 1, 'processing', first, 'Guardando'))
        monitor.handle_recording(('recording', 1, 'started', second, 'Grabando con audio'))
        monitor.recording_status.reset_mock()
        monitor.handle_recording(('recording', 1, 'saved', Path('movimiento_1.avi'), 'Guardado'))
        monitor.recording_status.set.assert_not_called()
        self.assertEqual(monitor.recording_active_path, second)

    def test_previous_clip_finishing_does_not_hide_a_recording_error(self):
        monitor = self.make_monitor()
        monitor.handle_recording(('recording', 1, 'error', None, 'Disco desconectado'))
        monitor.recording_status.reset_mock()
        monitor.handle_recording(('recording', 1, 'saved', Path('movimiento_1.avi'), 'Guardado'))
        monitor.recording_status.set.assert_not_called()
        self.assertTrue(monitor.recording_failed)

    def test_audio_warning_is_visible_without_marking_video_as_failed(self):
        monitor = self.make_monitor()
        path = Path('movimiento_1.grabando.avi')
        monitor.handle_recording(('recording', 1, 'started', path, 'Grabando con audio'))
        monitor.handle_recording(('recording', 1, 'audio_warning', path, 'Audio desactivado'))
        self.assertEqual(monitor.recording_active_path, path)
        self.assertFalse(monitor.recording_failed)
        self.assertTrue(monitor.recording_audio_disabled)
        self.assertIn('sin audio', monitor.recording_status.set.call_args.args[0])
        monitor.handle_recording(('recording', 1, 'saved', Path('movimiento_1.avi'), 'Clip sin audio guardado'))
        self.assertIsNone(monitor.recording_active_path)
        self.assertIn('audio desactivado', monitor.recording_status.set.call_args.args[0])
        monitor.handle_recording(('recording', 1, 'started', Path('movimiento_2.grabando.avi'), 'Grabando sin audio'))
        self.assertIn('audio desactivado', monitor.recording_status.set.call_args.args[0])

    def test_previous_session_audio_warning_cannot_disable_new_session_audio(self):
        monitor = self.make_monitor()
        monitor.handle_recording(('recording', 0, 'audio_warning', None, 'Audio desactivado'))
        self.assertFalse(monitor.recording_audio_disabled)
        monitor.recording_status.set.assert_not_called()


if __name__ == '__main__':
    unittest.main()
