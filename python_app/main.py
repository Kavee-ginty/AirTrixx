from __future__ import annotations

import time
import tkinter as tk

from config import load_app_config
from fusion_state import FusionState
from gui import AirTrixxGUI
from mediapipe_tracker import HandTracker
from serial_bridge import SerialBridge
from servo_controller import ServoController


CAMERA_FEED_START_TIMEOUT_S = 15.0
CAMERA_FEED_POLL_INTERVAL_S = 0.05
CAMERA_FEED_RETRY_MS = 100


def wait_for_camera_feed(hand_tracker: HandTracker, timeout_s: float = CAMERA_FEED_START_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_s)
    while time.monotonic() < deadline:
        if hand_tracker.latest_frame_is_visible():
            return True
        time.sleep(CAMERA_FEED_POLL_INTERVAL_S)
    return hand_tracker.latest_frame_is_visible()


def start_camera_centering_when_feed_ready(app: AirTrixxGUI, hand_tracker: HandTracker) -> None:
    if app.camera_centering_active or app.hand_calibration_active:
        return
    if not hand_tracker.latest_frame_is_visible():
        app.camera_centering_status_var.set("Camera centering: waiting for visible USB camera feed.")
        app.root.after(CAMERA_FEED_RETRY_MS, lambda: start_camera_centering_when_feed_ready(app, hand_tracker))
        return
    app.start_camera_centering()


def main() -> None:
    config = load_app_config()
    serial_bridge = SerialBridge(baud_rate=config.serial_baud)
    hand_tracker = HandTracker(
        camera_index=config.camera_index,
        width=config.camera_width,
        height=config.camera_height,
    )
    servo_controller = ServoController(
        serial_bridge,
        config.calibration,
        servo_min_tick=config.servo_min_tick,
        servo_max_tick=config.servo_max_tick,
        camera_width=config.camera_width,
        camera_height=config.camera_height,
        horizontal_fov_deg=config.horizontal_fov_deg,
        vertical_fov_deg=config.vertical_fov_deg,
    )
    fusion_state = FusionState()

    startup_logs: list[str] = []
    hand_tracker.on_log = startup_logs.append
    hand_tracker.start()
    camera_feed_ready = wait_for_camera_feed(hand_tracker)

    root = tk.Tk()
    app = AirTrixxGUI(root, config, serial_bridge, hand_tracker, servo_controller, fusion_state)
    for message in startup_logs:
        app.log(message)
    if camera_feed_ready:
        app.start_camera_centering()
    else:
        app.camera_centering_status_var.set("Camera centering: waiting for visible USB camera feed.")
        app.hand_calibration_status_var.set("Calibration phase: waiting for camera centering.")
        app.log("Visible USB camera feed did not load before startup timeout; centering will start when the feed appears.")
        root.after(CAMERA_FEED_RETRY_MS, lambda: start_camera_centering_when_feed_ready(app, hand_tracker))
    root.mainloop()
    del app


if __name__ == "__main__":
    main()
