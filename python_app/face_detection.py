from __future__ import annotations

import time
from typing import Any, Callable

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None

from vision_models import ensure_vision_models


FACE_SWITCH_AREA_RATIO = 1.25
FACE_LOCK_MAX_CENTER_DISTANCE = 0.28
FACE_SMOOTHING_ALPHA = 0.28
FACE_LOST_GRACE_S = 0.45
FACE_MIN_CONFIRM_FRAMES = 1
FACE_MIN_AREA_RATIO = 0.010
FACE_MAX_AREA_RATIO = 0.70
FACE_MIN_ASPECT = 0.62
FACE_MAX_ASPECT = 1.55
FACE_CENTER_TARGET_X = 0.50
FACE_CENTER_TARGET_Y = 0.38
FACE_CENTER_BIAS = 0.55


def empty_face_state() -> dict[str, Any]:
    return {
        "visible": False,
        "detected": False,
        "held": False,
        "x": None,
        "y": None,
        "top_y": None,
        "width": None,
        "height": None,
        "score": 0.0,
        "confidence": 0.0,
        "faces_seen": 0,
    }


def load_face_cascade() -> Any:
    if cv2 is None:
        return None
    for cascade_name in (
        "haarcascade_frontalface_default.xml",
        "haarcascade_frontalface_alt2.xml",
    ):
        cascade_path = cv2.data.haarcascades + cascade_name
        cascade = cv2.CascadeClassifier(cascade_path)
        if not cascade.empty():
            return cascade
    return None


def _prepare_face_gray(frame_bgr: Any) -> Any:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _merge_face_rects(faces_a: Any, faces_b: Any) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    for faces in (faces_a, faces_b):
        for face in faces:
            x, y, w, h = (int(value) for value in face)
            duplicate = False
            for existing in merged:
                ex, ey, ew, eh = existing
                overlap_x = max(0, min(x + w, ex + ew) - max(x, ex))
                overlap_y = max(0, min(y + h, ey + eh) - max(y, ey))
                overlap_area = overlap_x * overlap_y
                min_area = max(1, min(w * h, ew * eh))
                if overlap_area / min_area >= 0.45:
                    duplicate = True
                    break
            if not duplicate:
                merged.append((x, y, w, h))
    return merged


def detect_face_rects(detector: Any, frame_bgr: Any) -> list[tuple[int, int, int, int]]:
    if detector is None or cv2 is None:
        return []

    frame_h, frame_w = frame_bgr.shape[:2]
    min_side = max(40, int(min(frame_w, frame_h) * 0.05))
    gray = _prepare_face_gray(frame_bgr)
    equalized = cv2.equalizeHist(gray)

    params = {
        "scaleFactor": 1.08,
        "minNeighbors": 5,
        "flags": cv2.CASCADE_SCALE_IMAGE,
        "minSize": (min_side, min_side),
    }
    faces_a = detector.detectMultiScale(gray, **params)
    faces_b = detector.detectMultiScale(equalized, **params)
    return _merge_face_rects(faces_a, faces_b)


def face_state_from_rect(
    rect: tuple[int, int, int, int],
    frame_w: int,
    frame_h: int,
    faces_seen: int,
) -> dict[str, Any]:
    x, y, w, h = rect
    return {
        "visible": True,
        "detected": True,
        "held": False,
        "x": float((x + w / 2) / frame_w),
        "y": float((y + h / 2) / frame_h),
        "top_y": float(y / frame_h),
        "width": float(w / frame_w),
        "height": float(h / frame_h),
        "score": float(w * h),
        "confidence": 0.0,
        "faces_seen": int(faces_seen),
    }


def _face_center_distance(face: dict[str, Any], previous: dict[str, Any]) -> float:
    try:
        dx = float(face.get("x")) - float(previous.get("x"))
        dy = float(face.get("y")) - float(previous.get("y"))
    except (TypeError, ValueError):
        return 999.0
    return float((dx * dx + dy * dy) ** 0.5)


def _smooth_face_state(previous: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    smoothed = dict(selected)
    alpha = FACE_SMOOTHING_ALPHA
    for key in ("x", "y", "top_y", "width", "height"):
        previous_value = previous.get(key)
        selected_value = selected.get(key)
        if previous_value is None or selected_value is None:
            continue
        try:
            smoothed[key] = float(previous_value) + alpha * (
                float(selected_value) - float(previous_value)
            )
        except (TypeError, ValueError):
            pass
    return smoothed


def _candidate_quality(state: dict[str, Any]) -> float:
    width = float(state.get("width") or 0.0)
    height = float(state.get("height") or 0.0)
    if width <= 0.0 or height <= 0.0:
        return 0.0

    area = width * height
    if area < FACE_MIN_AREA_RATIO or area > FACE_MAX_AREA_RATIO:
        return 0.0

    aspect = width / max(height, 1e-6)
    if aspect < FACE_MIN_ASPECT or aspect > FACE_MAX_ASPECT:
        return 0.0

    try:
        cx = float(state.get("x"))
        cy = float(state.get("y"))
    except (TypeError, ValueError):
        return 0.0

    center_dist = ((cx - FACE_CENTER_TARGET_X) ** 2 + (cy - FACE_CENTER_TARGET_Y) ** 2) ** 0.5
    center_weight = max(0.15, 1.0 - center_dist * FACE_CENTER_BIAS)
    return area * center_weight


def select_best_face(
    faces: list[tuple[int, int, int, int]],
    frame_w: int,
    frame_h: int,
    previous: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, tuple[int, int, int, int] | None]:
    candidates: list[tuple[float, dict[str, Any], tuple[int, int, int, int]]] = []
    for rect in faces:
        state = face_state_from_rect(rect, frame_w, frame_h, len(faces))
        quality = _candidate_quality(state)
        if quality <= 0.0:
            continue
        state["confidence"] = quality
        candidates.append((quality, state, rect))

    if not candidates:
        return None, None

    best_quality, best_state, best_rect = max(candidates, key=lambda item: item[0])
    selected_quality = best_quality
    selected_state = best_state
    selected_rect = best_rect
    selected_is_previous = False

    if previous and previous.get("visible"):
        previous_candidate = min(
            candidates,
            key=lambda item: _face_center_distance(item[1], previous),
        )
        previous_distance = _face_center_distance(previous_candidate[1], previous)
        previous_quality = previous_candidate[0]
        if (
            previous_distance <= FACE_LOCK_MAX_CENTER_DISTANCE
            and best_quality <= previous_quality * FACE_SWITCH_AREA_RATIO
        ):
            selected_quality, selected_state, selected_rect = previous_candidate
            selected_is_previous = True

    if previous and (selected_is_previous or previous.get("visible")):
        selected_state = _smooth_face_state(previous, selected_state)
    selected_state["confidence"] = selected_quality
    selected_state["faces_seen"] = len(faces)
    return selected_state, selected_rect


class MediaPipeFaceBackend:
    """BlazeFace detector via MediaPipe Tasks."""

    def __init__(self, on_log: Callable[[str], None] | None = None) -> None:
        self._detector: Any | None = None
        self._ready = False
        face_path, _ = ensure_vision_models(on_log)
        if face_path is None or cv2 is None or np is None:
            return
        try:
            from mediapipe.tasks.python.vision import face_detector as face_detector_module

            self._detector = face_detector_module.FaceDetector.create_from_model_path(str(face_path))
            self._ready = True
            if on_log:
                on_log("MediaPipe face detector ready.")
        except Exception as exc:
            if on_log:
                on_log(f"Could not start MediaPipe face detector: {exc}")

    @property
    def ready(self) -> bool:
        return self._ready

    def close(self) -> None:
        if self._detector is not None:
            self._detector.close()
            self._detector = None
        self._ready = False

    def detect_rects(self, frame_bgr: Any) -> list[tuple[int, int, int, int]]:
        if not self._ready or self._detector is None or frame_bgr is None:
            return []
        try:
            from mediapipe.tasks.python.vision.core import image as mp_image_module
        except Exception:
            return []

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp_image_module.Image(
            image_format=mp_image_module.ImageFormat.SRGB,
            data=np.ascontiguousarray(frame_rgb),
        )
        result = self._detector.detect(mp_image)
        frame_h, frame_w = frame_bgr.shape[:2]
        rects: list[tuple[int, int, int, int]] = []
        for detection in result.detections:
            bbox = detection.bounding_box
            x = int(max(0, bbox.origin_x))
            y = int(max(0, bbox.origin_y))
            w = int(max(1, bbox.width))
            h = int(max(1, bbox.height))
            if x + w > frame_w:
                w = max(1, frame_w - x)
            if y + h > frame_h:
                h = max(1, frame_h - y)
            rects.append((x, y, w, h))
        return rects


class FaceDetectionEngine:
    """Detect, score, smooth, and briefly hold face tracks across noisy frames."""

    def __init__(self, on_log: Callable[[str], None] | None = None) -> None:
        self._mp_backend = MediaPipeFaceBackend(on_log)
        self._haar_detector = None if self._mp_backend.ready else load_face_cascade()
        self._tracked_face: dict[str, Any] | None = None
        self._published_face = empty_face_state()
        self._confirm_streak = 0
        self._last_detection_s = 0.0

    @property
    def detector_ready(self) -> bool:
        return self._mp_backend.ready or self._haar_detector is not None

    def reset(self) -> None:
        self._tracked_face = None
        self._published_face = empty_face_state()
        self._confirm_streak = 0
        self._last_detection_s = 0.0

    def close(self) -> None:
        self._mp_backend.close()

    def _detect_rects(self, frame_bgr: Any) -> list[tuple[int, int, int, int]]:
        if self._mp_backend.ready:
            return self._mp_backend.detect_rects(frame_bgr)
        if self._haar_detector is not None:
            return detect_face_rects(self._haar_detector, frame_bgr)
        return []

    def update(self, frame_bgr: Any) -> tuple[dict[str, Any], tuple[int, int, int, int] | None]:
        if not self.detector_ready or frame_bgr is None:
            self.reset()
            return empty_face_state(), None

        frame_h, frame_w = frame_bgr.shape[:2]
        rects = self._detect_rects(frame_bgr)
        now = time.monotonic()

        if rects:
            selected_state, selected_rect = select_best_face(
                rects,
                frame_w,
                frame_h,
                self._tracked_face,
            )
            if selected_state is not None and selected_rect is not None:
                self._confirm_streak += 1
                self._last_detection_s = now
                if self._confirm_streak >= FACE_MIN_CONFIRM_FRAMES:
                    selected_state["visible"] = True
                    selected_state["detected"] = True
                    selected_state["held"] = False
                    self._tracked_face = dict(selected_state)
                    self._published_face = dict(selected_state)
                else:
                    warming = dict(selected_state)
                    warming["visible"] = False
                    warming["detected"] = True
                    warming["held"] = False
                    self._published_face = warming
                return self._published_face, selected_rect

        self._confirm_streak = 0
        if self._tracked_face and now - self._last_detection_s <= FACE_LOST_GRACE_S:
            held = dict(self._tracked_face)
            held["visible"] = True
            held["detected"] = False
            held["held"] = True
            self._published_face = held
            return held, None

        self._tracked_face = None
        self._published_face = empty_face_state()
        return self._published_face, None
