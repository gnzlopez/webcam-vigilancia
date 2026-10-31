"""Motion analysis independent of the camera and graphical interface."""
import cv2
import numpy as np


class MotionDetector:
    def __init__(self, warmup=3.0):
        self.background = None
        self.started = None
        self.since = None
        self.last_event = float('-inf')
        self.warmup = warmup
        self.confirmed_motion = False

    def update(self, frame, now, sensitivity=50):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (9, 9), 0)
        if self.background is None:
            self.background = gray.astype(np.float32)
            self.started = now
        calibrating = now - self.started < self.warmup
        delta = cv2.absdiff(gray, cv2.convertScaleAbs(self.background))
        mask = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.dilate(mask, None, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        minimum = frame.shape[0] * frame.shape[1] * (0.025 - sensitivity * 0.00023)
        boxes = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= minimum]
        moving = bool(boxes) and not calibrating
        if moving:
            if self.since is None:
                self.since = now
        else:
            self.since = None
        self.confirmed_motion = moving and now - self.since >= 0.3
        event = self.confirmed_motion and now - self.last_event >= 3
        if event:
            self.last_event = now
        cv2.accumulateWeighted(gray, self.background, 0.15 if calibrating else 0.015)
        return boxes if not calibrating else [], moving, event, calibrating
