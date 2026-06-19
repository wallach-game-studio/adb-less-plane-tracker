"""Home Assistant pan/tilt readout, RTSP frame grabbing, and blob detection."""
from __future__ import annotations

import cv2
import numpy as np
import requests

from tracker.config import CameraConfig, DetectionConfig, HomeAssistantConfig


class HomeAssistantClient:
    def __init__(self, config: HomeAssistantConfig):
        self._base_url = config.url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {config.token}",
            "Content-Type": "application/json",
        }

    def get_state(self, entity_id: str) -> float:
        response = requests.get(
            f"{self._base_url}/api/states/{entity_id}", headers=self._headers, timeout=5
        )
        response.raise_for_status()
        return float(response.json()["state"])

    def get_pan_tilt(self, camera: CameraConfig) -> tuple[float, float]:
        pan = self.get_state(camera.pan_entity)
        tilt = self.get_state(camera.tilt_entity)
        return pan, tilt


class CameraStream:
    """Holds an open RTSP capture for a single camera, grabbing latest frames on demand."""

    def __init__(self, camera: CameraConfig):
        self._camera = camera
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        self._capture = cv2.VideoCapture(self._camera.rtsp)

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def read_frame(self) -> np.ndarray | None:
        if self._capture is None:
            self.open()
        ok, frame = self._capture.read()
        return frame if ok else None


def make_blob_detector(detection: DetectionConfig) -> cv2.SimpleBlobDetector:
    params = cv2.SimpleBlobDetector_Params()
    params.filterByArea = True
    params.minArea = detection.min_area
    params.maxArea = detection.max_area
    params.filterByColor = True
    params.blobColor = detection.blob_color
    return cv2.SimpleBlobDetector_create(params)


def crop_roi(frame: np.ndarray, px: int, py: int, roi_r: int) -> tuple[np.ndarray, int, int]:
    """Crop a square ROI around (px, py); returns the crop plus its top-left offset."""
    h, w = frame.shape[:2]
    x0, y0 = max(0, px - roi_r), max(0, py - roi_r)
    x1, y1 = min(w, px + roi_r), min(h, py + roi_r)
    return frame[y0:y1, x0:x1], x0, y0


def detect_blob_near(
    frame: np.ndarray,
    predicted_px: int,
    predicted_py: int,
    detector: cv2.SimpleBlobDetector,
    detection: DetectionConfig,
) -> tuple[int, int] | None:
    """Detect a blob within the ROI; return its absolute pixel position if within ACCEPT_RADIUS."""
    roi, x0, y0 = crop_roi(frame, predicted_px, predicted_py, detection.roi_r)
    if roi.size == 0:
        return None

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    keypoints = detector.detect(gray)
    if not keypoints:
        return None

    best = min(keypoints, key=lambda kp: (kp.pt[0] - detection.roi_r) ** 2 + (kp.pt[1] - detection.roi_r) ** 2)
    abs_px, abs_py = int(x0 + best.pt[0]), int(y0 + best.pt[1])

    distance = ((abs_px - predicted_px) ** 2 + (abs_py - predicted_py) ** 2) ** 0.5
    if distance > detection.accept_radius:
        return None
    return abs_px, abs_py
