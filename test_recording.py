"""Check real video files and the motion/recording boundary with synthetic frames."""
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from app import Monitor
from recording import MotionRecorder, RecordingConfig


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = RecordingConfig(Path(self.temp.name) / 'cámara y clips', 1)
        self.config.prepare()
        self.reports = []
        self.recorder = MotionRecorder(self.config, lambda *item: self.reports.append(item))
        self.addCleanup(self.recorder.close)
        self.frame = np.full((48, 64, 3), 120, np.uint8)

    def sample(self, now, moving=False, confirmed=False):
        self.recorder.update(self.frame, now, moving, confirmed)

    def videos(self):
        return [path for kind, path, _ in self.reports if kind == 'saved']

    def inspect(self, path):
        reader = cv2.VideoCapture(str(path))
        try:
            self.assertTrue(reader.isOpened())
            fps = reader.get(cv2.CAP_PROP_FPS)
            count = 0
            while True:
                ok, frame = reader.read()
                if not ok:
                    break
                count += 1
                self.assertEqual(frame.shape, self.frame.shape)
            self.assertGreater(count, 0)
            return count, fps
        finally:
            reader.release()

    def test_unconfirmed_motion_does_not_create_files(self):
        self.sample(0, True, False)
        self.sample(.2, False, False)
        self.recorder.close()
        self.assertEqual(list(self.config.folder.iterdir()), [])

    def test_motion_extends_one_clip_then_new_episode_creates_another(self):
        self.sample(0, True, True)
        self.sample(.7)
        self.sample(.9, True, False)
        self.sample(1.2)
        self.assertEqual(self.videos(), [])
        self.sample(1.9)
        self.assertEqual(len(self.videos()), 1)
        count, fps = self.inspect(self.videos()[0])
        self.assertAlmostEqual(count / fps, 1.9)
        self.sample(3, True, True)
        self.recorder.close()
        self.assertEqual(len(set(self.videos())), 2)
        self.assertFalse(list(self.config.folder.glob('*.grabando.avi')))

    def test_irregular_camera_cadence_preserves_video_duration(self):
        self.sample(0, True, True)
        for now in (.035, .18, .24, .39, .43, .68, .85, 1.01):
            self.sample(now)
        count, fps = self.inspect(self.videos()[0])
        self.assertEqual(count, 10)
        self.assertEqual(fps, 10)

    def test_stop_finalizes_current_clip_and_close_is_idempotent(self):
        self.sample(0, True, True)
        self.sample(.3, True, True)
        self.recorder.close()
        self.recorder.close()
        self.assertEqual(len(self.videos()), 1)
        self.assertEqual(self.inspect(self.videos()[0])[0], 4)

    def test_continuous_motion_splits_at_maximum_without_waiting_for_a_new_event(self):
        self.recorder.MAX_SECONDS = 1
        for now in (0, .4, .8, 1, 1.4):
            self.sample(now, True, True)
        self.recorder.close()
        self.assertEqual(len(self.videos()), 2)
        self.assertEqual(self.inspect(self.videos()[0])[0], 10)
        self.assertEqual(self.inspect(self.videos()[1])[0], 5)

    def test_capture_gap_does_not_generate_minutes_of_duplicate_frames(self):
        self.sample(0, True, True)
        self.sample(.5, True, True)
        self.sample(600, True, True)
        self.recorder.close()
        self.assertEqual(len(self.videos()), 2)
        self.assertEqual(self.inspect(self.videos()[0])[0], 6)
        self.assertEqual(self.inspect(self.videos()[1])[0], 1)

    def test_low_disk_space_reports_once_and_disables_only_the_recorder(self):
        with patch('recording.shutil.disk_usage', return_value=Mock(free=1)):
            self.sample(0, True, True)
            self.sample(1, True, True)
        self.assertTrue(self.recorder.failed)
        self.assertEqual([r[0] for r in self.reports], ['error'])
        self.assertIn('La detección continúa', self.reports[0][2])
        self.assertEqual(list(self.config.folder.iterdir()), [])

    def test_encoder_failure_does_not_report_a_successful_clip(self):
        writer = Mock()
        writer.isOpened.return_value = False
        with patch('recording.cv2.VideoWriter', return_value=writer):
            self.sample(0, True, True)
        writer.release.assert_called_once()
        self.assertTrue(self.recorder.failed)
        self.assertEqual([r[0] for r in self.reports], ['error'])
        self.assertEqual(self.videos(), [])

    def test_write_failure_retains_partial_file_and_closes_writer(self):
        writer = Mock()
        writer.write.side_effect = OSError('Disco desconectado')
        with patch('recording.cv2.VideoWriter', return_value=writer):
            self.sample(0, True, True)
        writer.release.assert_called_once()
        self.assertEqual([r[0] for r in self.reports], ['started', 'error'])
        self.assertTrue(self.reports[-1][1].exists())
        self.assertEqual(self.videos(), [])

    def test_invalid_settings_and_unwritable_destination_are_rejected(self):
        for seconds in (0, 61, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                RecordingConfig(self.config.folder, seconds)
        file = self.config.folder / 'archivo.txt'
        file.write_text('No es una carpeta')
        with self.assertRaises(OSError):
            RecordingConfig(file).prepare()


class CaptureRecordingTests(unittest.TestCase):
    def make_monitor(self, config):
        monitor = Monitor.__new__(Monitor)
        monitor.options = (50, False, True, 1, config)
        monitor.stop = threading.Event()
        monitor.events = queue.Queue()
        monitor.publish = Mock()
        return monitor

    def test_calibration_is_not_recorded_and_stopping_vigilance_closes_clip(self):
        monitor = self.make_monitor(RecordingConfig(Path(tempfile.gettempdir())))
        camera = Mock()
        frame = np.zeros((480, 640, 3), np.uint8)
        reads = 0

        def read():
            nonlocal reads
            reads += 1
            if reads == 3:
                monitor.options = (50, False, False, 2, None)
            if reads == 4:
                monitor.stop.set()
            return True, frame.copy()

        camera.read.side_effect = read
        detector = Mock(confirmed_motion=True)
        detector.update.side_effect = [([], False, False, True), ([(10, 10, 40, 40)], True, True, False)]
        with patch('app.cv2.VideoCapture', return_value=camera), \
                patch('app.MotionDetector', return_value=detector), \
                patch('app.MotionRecorder') as recorder_type:
            recorder = recorder_type.return_value
            recorder.update.side_effect = lambda received, *args: self.assertFalse(received.any())
            monitor.capture(0)
        recorder.update.assert_called_once()
        recorder.close.assert_called_once()
        camera.release.assert_called_once()

    def test_camera_failure_finalizes_recording(self):
        monitor = self.make_monitor(RecordingConfig(Path(tempfile.gettempdir())))
        camera = Mock()
        camera.read.side_effect = [(True, np.zeros((480, 640, 3), np.uint8)), (False, None)]
        detector = Mock(confirmed_motion=True)
        detector.update.return_value = ([], True, True, False)
        with patch('app.cv2.VideoCapture', return_value=camera), \
                patch('app.MotionDetector', return_value=detector), \
                patch('app.MotionRecorder') as recorder_type:
            monitor.capture(0)
        recorder_type.return_value.close.assert_called_once()
        self.assertIn('error', [item[0] for item in list(monitor.events.queue)])


if __name__ == '__main__':
    unittest.main()
