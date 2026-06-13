from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mediapipe_tracker import classify_hand_gesture


def make_landmarks() -> list[SimpleNamespace]:
    points = [SimpleNamespace(x=0.5, y=0.8) for _ in range(21)]
    points[0] = SimpleNamespace(x=0.5, y=0.9)
    points[5] = SimpleNamespace(x=0.45, y=0.6)
    points[6] = SimpleNamespace(x=0.45, y=0.5)
    points[8] = SimpleNamespace(x=0.45, y=0.36)
    points[9] = SimpleNamespace(x=0.5, y=0.62)
    points[10] = SimpleNamespace(x=0.5, y=0.52)
    points[12] = SimpleNamespace(x=0.5, y=0.38)
    points[13] = SimpleNamespace(x=0.55, y=0.64)
    points[14] = SimpleNamespace(x=0.55, y=0.54)
    points[16] = SimpleNamespace(x=0.55, y=0.4)
    points[17] = SimpleNamespace(x=0.6, y=0.66)
    points[18] = SimpleNamespace(x=0.6, y=0.56)
    points[20] = SimpleNamespace(x=0.6, y=0.42)
    points[2] = SimpleNamespace(x=0.36, y=0.72)
    points[3] = SimpleNamespace(x=0.3, y=0.64)
    points[4] = SimpleNamespace(x=0.23, y=0.55)
    return points


def curl_finger(landmarks: list[SimpleNamespace], tip_index: int, pip_index: int, x: float) -> None:
    landmarks[pip_index] = SimpleNamespace(x=x, y=0.55)
    landmarks[tip_index] = SimpleNamespace(x=x, y=0.68)


class MediaPipeGestureClassificationTests(unittest.TestCase):
    def test_recognises_thumb_up(self) -> None:
        landmarks = make_landmarks()
        curl_finger(landmarks, 8, 6, 0.45)
        curl_finger(landmarks, 12, 10, 0.5)
        curl_finger(landmarks, 16, 14, 0.55)
        curl_finger(landmarks, 20, 18, 0.6)
        landmarks[3] = SimpleNamespace(x=0.33, y=0.54)
        landmarks[4] = SimpleNamespace(x=0.35, y=0.34)

        self.assertEqual(classify_hand_gesture(landmarks), "thumb_up")

    def test_recognises_gun_gesture(self) -> None:
        landmarks = make_landmarks()
        curl_finger(landmarks, 12, 10, 0.5)
        curl_finger(landmarks, 16, 14, 0.55)
        curl_finger(landmarks, 20, 18, 0.6)
        landmarks[3] = SimpleNamespace(x=0.3, y=0.62)
        landmarks[4] = SimpleNamespace(x=0.18, y=0.52)

        self.assertEqual(classify_hand_gesture(landmarks), "gun_gesture")

    def test_recognises_peace_sign(self) -> None:
        landmarks = make_landmarks()
        curl_finger(landmarks, 16, 14, 0.55)
        curl_finger(landmarks, 20, 18, 0.6)
        landmarks[4] = SimpleNamespace(x=0.3, y=0.62)

        self.assertEqual(classify_hand_gesture(landmarks), "peace_sign")

    def test_recognises_index_thumb_pinch(self) -> None:
        landmarks = make_landmarks()
        curl_finger(landmarks, 12, 10, 0.5)
        curl_finger(landmarks, 16, 14, 0.55)
        curl_finger(landmarks, 20, 18, 0.6)
        landmarks[6] = SimpleNamespace(x=0.43, y=0.5)
        landmarks[8] = SimpleNamespace(x=0.39, y=0.47)
        landmarks[3] = SimpleNamespace(x=0.35, y=0.52)
        landmarks[4] = SimpleNamespace(x=0.4, y=0.48)

        self.assertEqual(classify_hand_gesture(landmarks), "index_thumb_pinch")

    def test_keeps_index_finger_up(self) -> None:
        landmarks = make_landmarks()
        curl_finger(landmarks, 12, 10, 0.5)
        curl_finger(landmarks, 16, 14, 0.55)
        curl_finger(landmarks, 20, 18, 0.6)
        landmarks[4] = SimpleNamespace(x=0.28, y=0.64)

        self.assertEqual(classify_hand_gesture(landmarks), "index_finger_up")

    def test_index_finger_up_does_not_turn_into_pinch_when_thumb_is_nearby(self) -> None:
        landmarks = make_landmarks()
        curl_finger(landmarks, 12, 10, 0.5)
        curl_finger(landmarks, 16, 14, 0.55)
        curl_finger(landmarks, 20, 18, 0.6)
        landmarks[3] = SimpleNamespace(x=0.35, y=0.56)
        landmarks[4] = SimpleNamespace(x=0.34, y=0.56)
        landmarks[8] = SimpleNamespace(x=0.44, y=0.42)

        self.assertEqual(classify_hand_gesture(landmarks), "index_finger_up")


if __name__ == "__main__":
    unittest.main()
