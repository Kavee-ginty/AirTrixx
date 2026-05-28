from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None

from gesture_utils import classify_hand_gesture
from vision_models import ensure_vision_models


LogCallback = Callable[[str], None]

HAND_CONNECTIONS: list[tuple[int, int]] = [
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (0, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (0, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (0, 17),
    (17, 18),
    (18, 19),
    (19, 20),
    (5, 9),
    (9, 13),
    (13, 17),
]

HAND_COLORS = {
    "left": ((255, 80, 80), (255, 160, 160)),
    "right": ((80, 160, 255), (160, 210, 255)),
}


@dataclass
class _LandmarkPoint:
    x: float
    y: float
    z: float = 0.0


def _empty_hand_state() -> dict[str, dict[str, Any]]:
    return {
        "right": {"visible": False, "x": None, "y": None, "score": 0.0, "gesture": "none"},
        "left": {"visible": False, "x": None, "y": None, "score": 0.0, "gesture": "none"},
    }


def _landmark_px(
    landmark: Any,
    frame_w: int,
    frame_h: int,
) -> tuple[int, int] | None:
    x = int(landmark.x * frame_w)
    y = int(landmark.y * frame_h)
    if x < 0 or y < 0 or x >= frame_w or y >= frame_h:
        return None
    return x, y


def draw_hand_landmarks(frame_bgr: Any, side: str, landmarks: list[Any]) -> None:
    if cv2 is None or not landmarks:
        return
    frame_h, frame_w = frame_bgr.shape[:2]
    line_color, dot_color = HAND_COLORS.get(side, ((0, 255, 0), (180, 255, 180)))

    points: dict[int, tuple[int, int]] = {}
    for index, landmark in enumerate(landmarks):
        px = _landmark_px(landmark, frame_w, frame_h)
        if px is not None:
            points[index] = px

    for start_idx, end_idx in HAND_CONNECTIONS:
        if start_idx in points and end_idx in points:
            cv2.line(frame_bgr, points[start_idx], points[end_idx], line_color, 2, cv2.LINE_AA)

    for px in points.values():
        cv2.circle(frame_bgr, px, 4, dot_color, -1, lineType=cv2.LINE_AA)
        cv2.circle(frame_bgr, px, 4, line_color, 1, lineType=cv2.LINE_AA)


class HandTrackingEngine:
    """MediaPipe Tasks hand landmarker with overlay drawing and gesture labels."""

    def __init__(self, on_log: LogCallback | None = None) -> None:
        self.on_log = on_log
        self._landmarker: Any | None = None
        self._frame_timestamp_ms = 0
        self._ready = False
        self._init()

    @property
    def ready(self) -> bool:
        return self._ready

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
        self._ready = False

    def _init(self) -> None:
        if cv2 is None or np is None:
            return
        try:
            from mediapipe.tasks.python.core import base_options as base_options_module
            from mediapipe.tasks.python.vision import hand_landmarker
            from mediapipe.tasks.python.vision.core import vision_task_running_mode as running_mode_module
        except Exception as exc:
            if self.on_log:
                self.on_log(f"MediaPipe hand tasks unavailable: {exc}")
            return

        _, hand_path = ensure_vision_models(self.on_log)
        if hand_path is None:
            if self.on_log:
                self.on_log("Hand landmarker model is missing.")
            return

        options = hand_landmarker.HandLandmarkerOptions(
            base_options=base_options_module.BaseOptions(model_asset_path=str(hand_path)),
            running_mode=running_mode_module.VisionTaskRunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.45,
            min_hand_presence_confidence=0.45,
            min_tracking_confidence=0.45,
        )
        try:
            self._landmarker = hand_landmarker.HandLandmarker.create_from_options(options)
            self._ready = True
            if self.on_log:
                self.on_log("MediaPipe hand landmarker ready.")
        except Exception as exc:
            if self.on_log:
                self.on_log(f"Could not start hand landmarker: {exc}")

    def process(self, frame_bgr: Any) -> dict[str, dict[str, Any]]:
        state = _empty_hand_state()
        if not self._ready or self._landmarker is None or frame_bgr is None:
            return state

        try:
            from mediapipe.tasks.python.vision.core import image as mp_image_module
        except Exception:
            return state

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp_image_module.Image(
            image_format=mp_image_module.ImageFormat.SRGB,
            data=np.ascontiguousarray(frame_rgb),
        )
        self._frame_timestamp_ms = int(time.monotonic() * 1000)
        result = self._landmarker.detect_for_video(mp_image, self._frame_timestamp_ms)

        if not result.hand_landmarks:
            return state

        for hand_landmarks, handedness_list in zip(result.hand_landmarks, result.handedness):
            if not hand_landmarks or not handedness_list:
                continue
            label = handedness_list[0].category_name.lower()
            if label == "right":
                side = "left"
            elif label == "left":
                side = "right"
            else:
                continue

            score = float(handedness_list[0].score or 0.0)
            xs = [lm.x for lm in hand_landmarks]
            ys = [lm.y for lm in hand_landmarks]
            landmark_points = [_LandmarkPoint(lm.x, lm.y, getattr(lm, "z", 0.0)) for lm in hand_landmarks]
            gesture = classify_hand_gesture(landmark_points)
            draw_hand_landmarks(frame_bgr, side, hand_landmarks)

            if score >= state[side]["score"]:
                state[side] = {
                    "visible": True,
                    "x": float(sum(xs) / len(xs)),
                    "y": float(sum(ys) / len(ys)),
                    "score": score,
                    "gesture": gesture,
                    "landmark_count": len(hand_landmarks),
                }

        return state
