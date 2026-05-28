from __future__ import annotations

import threading
import time
from typing import Any, Callable

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

try:
    import mediapipe as mp
except Exception:  # pragma: no cover
    mp = None

from face_detection import FaceDetectionEngine, empty_face_state
from hand_tracking import HandTrackingEngine


LogCallback = Callable[[str], None]


def _empty_hand_state() -> dict[str, dict[str, Any]]:
    return {
        "right": {"visible": False, "x": None, "y": None, "score": 0.0, "gesture": "none"},
        "left": {"visible": False, "x": None, "y": None, "score": 0.0, "gesture": "none"},
    }


class HandTracker:
    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        on_log: LogCallback | None = None,
    ) -> None:
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.on_log = on_log
        self.mirror_preview = True
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest_hands = _empty_hand_state()
        self._latest_face = empty_face_state()
        self._face_engine = FaceDetectionEngine(on_log=self._log)
        self._hand_engine = HandTrackingEngine(on_log=self._log)
        self._latest_frame_rgb: np.ndarray | None = None

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if cv2 is None:
            self._log("OpenCV is missing. Run pip install -r requirements.txt.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._face_engine.close()
        self._hand_engine.close()

    def configure(self, camera_index: int | None = None, mirror_preview: bool | None = None) -> None:
        restart = camera_index is not None and camera_index != self.camera_index
        if mirror_preview is not None:
            self.mirror_preview = bool(mirror_preview)
        if camera_index is not None:
            self.camera_index = int(camera_index)
        if restart:
            was_running = bool(self._thread and self._thread.is_alive())
            self.stop()
            self._face_engine = FaceDetectionEngine(on_log=self._log)
            self._hand_engine = HandTrackingEngine(on_log=self._log)
            with self._lock:
                self._latest_hands = _empty_hand_state()
                self._latest_face = empty_face_state()
                self._face_engine.reset()
                self._latest_frame_rgb = None
            if was_running:
                self._stop_event.clear()
                self.start()

    def get_latest_hands(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                side: dict(values)
                for side, values in self._latest_hands.items()
            }

    def get_latest_frame_rgb(self) -> np.ndarray | None:
        with self._lock:
            if self._latest_frame_rgb is None:
                return None
            return self._latest_frame_rgb.copy()

    def get_latest_face(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._latest_face)

    def _draw_face_overlay(
        self,
        frame_bgr: Any,
        face_state: dict[str, Any],
        selected_rect: tuple[int, int, int, int] | None,
    ) -> None:
        if cv2 is None:
            return
        if selected_rect is not None:
            sx, sy, sw, sh = selected_rect
            color = (40, 180, 255) if face_state.get("held") else (60, 220, 120)
            cv2.rectangle(frame_bgr, (int(sx), int(sy)), (int(sx + sw), int(sy + sh)), color, 2)
            label = "face"
            if face_state.get("held"):
                label = "face (held)"
            cv2.putText(
                frame_bgr,
                label,
                (int(sx), max(18, int(sy) - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )
        elif face_state.get("visible") and face_state.get("x") is not None:
            frame_h, frame_w = frame_bgr.shape[:2]
            cx = int(float(face_state["x"]) * frame_w)
            cy = int(float(face_state.get("y") or face_state.get("top_y") or 0.5) * frame_h)
            cv2.circle(frame_bgr, (cx, cy), 6, (40, 180, 255), 2)

    def _draw_gesture_labels(self, frame_bgr: Any, hands: dict[str, dict[str, Any]]) -> None:
        if cv2 is None:
            return
        frame_h, frame_w = frame_bgr.shape[:2]
        for side, color in (("left", (255, 120, 120)), ("right", (120, 180, 255))):
            values = hands.get(side, {})
            if not values.get("visible") or values.get("x") is None or values.get("y") is None:
                continue
            px = int(float(values["x"]) * frame_w)
            py = int(float(values["y"]) * frame_h)
            gesture = str(values.get("gesture") or "none")
            cv2.putText(
                frame_bgr,
                f"{side}: {gesture}",
                (max(8, px - 40), max(20, py - 18)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )

    def _run(self) -> None:
        camera_index = self.camera_index
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            self._log(f"Could not open camera index {camera_index}.")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not self._face_engine.detector_ready:
            self._log("Face detector could not be loaded.")
        if not self._hand_engine.ready:
            self._log("Hand landmarker is not ready; face-only mode.")

        version = getattr(mp, "__version__", "unknown") if mp else "not installed"
        self._log(
            f"Camera tracker started on index {camera_index} "
            f"(mediapipe={version}, face={'ok' if self._face_engine.detector_ready else 'off'}, "
            f"hands={'ok' if self._hand_engine.ready else 'off'})."
        )

        try:
            while not self._stop_event.is_set():
                ok, frame_bgr = cap.read()
                if not ok:
                    time.sleep(0.03)
                    continue

                hands = self._hand_engine.process(frame_bgr)
                face_state, selected_rect = self._face_engine.update(frame_bgr)
                self._draw_face_overlay(frame_bgr, face_state, selected_rect)
                self._draw_gesture_labels(frame_bgr, hands)

                annotated_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                if self.mirror_preview:
                    annotated_rgb = np.ascontiguousarray(np.flip(annotated_rgb, axis=1))
                with self._lock:
                    self._latest_hands = hands
                    self._latest_face = face_state
                    self._latest_frame_rgb = annotated_rgb
        finally:
            cap.release()
            self._face_engine.close()
            self._hand_engine.close()
            self._log("Camera tracker stopped.")
