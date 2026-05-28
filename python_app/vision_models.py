from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
MODEL_DIR = APP_DIR / "models"

FACE_MODEL_NAME = "blaze_face_short_range.tflite"
HAND_MODEL_NAME = "hand_landmarker.task"

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
)
HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)


def ensure_vision_models(on_log: Any | None = None) -> tuple[Path | None, Path | None]:
    """Download MediaPipe task models if missing. Returns (face_path, hand_path)."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    face_path = MODEL_DIR / FACE_MODEL_NAME
    hand_path = MODEL_DIR / HAND_MODEL_NAME

    for url, path, label in (
        (FACE_MODEL_URL, face_path, "face detector"),
        (HAND_MODEL_URL, hand_path, "hand landmarker"),
    ):
        if path.exists() and path.stat().st_size > 0:
            continue
        if on_log:
            on_log(f"Downloading {label} model...")
        try:
            urllib.request.urlretrieve(url, path)
            if on_log:
                on_log(f"Saved {path.name}.")
        except Exception as exc:
            if on_log:
                on_log(f"Could not download {label} model: {exc}")
            if path.exists():
                path.unlink(missing_ok=True)

    face_ok = face_path.exists() and face_path.stat().st_size > 0
    hand_ok = hand_path.exists() and hand_path.stat().st_size > 0
    return (face_path if face_ok else None, hand_path if hand_ok else None)
