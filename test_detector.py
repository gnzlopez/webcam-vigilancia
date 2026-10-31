import unittest
import numpy as np
from detector import MotionDetector


class DetectorTests(unittest.TestCase):
    def test_static_scene(self):
        detector = MotionDetector(warmup=0)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for instant in (0, 1, 2, 3, 4):
            _, moving, event, _ = detector.update(frame, instant)
            self.assertFalse(moving)
            self.assertFalse(event)

    def test_sustained_motion_and_cooldown(self):
        detector = MotionDetector(warmup=0)
        empty = np.zeros((240, 320, 3), dtype=np.uint8)
        detector.update(empty, 0)
        changed = empty.copy()
        changed[40:160, 40:160] = 255
        self.assertFalse(detector.update(changed, 1)[2])
        self.assertTrue(detector.update(changed, 1.4)[2])
        self.assertFalse(detector.update(changed, 2)[2])
        self.assertTrue(detector.update(changed, 4.5)[2])

    def test_warmup_suppresses_events(self):
        detector = MotionDetector(warmup=3)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        detector.update(frame, 0)
        frame[30:180, 30:180] = 255
        _, moving, event, calibrating = detector.update(frame, 1)
        self.assertTrue(calibrating)
        self.assertFalse(moving)
        self.assertFalse(event)

    def test_confirmation_is_independent_of_log_cooldown(self):
        detector = MotionDetector(warmup=0)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        detector.update(frame, 0)
        frame[40:160, 40:160] = 255
        detector.update(frame, 1)
        self.assertFalse(detector.confirmed_motion)
        self.assertTrue(detector.update(frame, 1.4)[2])
        self.assertFalse(detector.update(frame, 1.5)[2])
        self.assertTrue(detector.confirmed_motion)


if __name__ == '__main__':
    unittest.main()
