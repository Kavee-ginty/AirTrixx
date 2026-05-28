from __future__ import annotations

from typing import Any


def _finger_is_extended(landmarks: Any, tip_index: int, pip_index: int) -> bool:
    return landmarks[tip_index].y < landmarks[pip_index].y - 0.025


def classify_hand_gesture(landmarks: Any) -> str:
    index_up = _finger_is_extended(landmarks, 8, 6)
    middle_up = _finger_is_extended(landmarks, 12, 10)
    ring_up = _finger_is_extended(landmarks, 16, 14)
    pinky_up = _finger_is_extended(landmarks, 20, 18)
    extended_count = sum([index_up, middle_up, ring_up, pinky_up])

    if extended_count >= 4:
        return "open_palm"
    if index_up and not middle_up and not ring_up and not pinky_up:
        return "index_finger_up"
    if extended_count == 0:
        return "closed_fist"
    return "unknown"
