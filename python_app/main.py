from __future__ import annotations

import os
import sys


def _ensure_supported_python() -> None:
    if sys.version_info >= (3, 13):
        raise SystemExit(
            "AirTrixx must be run with Python 3.11 or 3.12. "
            "The current Python is "
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}. "
            "Create the app environment with: "
            "/opt/homebrew/bin/python3.11 -m venv .venv"
        )


def main() -> None:
    _ensure_supported_python()

    from app_controller import AirTrixxController
    from app_paths import project_resource_path
    from config import load_app_config
    from fusion_state import FusionState
    from mediapipe_tracker import HandTracker
    from runtime_acceleration import request_windows_high_performance_gpu
    from serial_bridge import SerialBridge
    from servo_controller import ServoController
    from web_api import AirTrixxWebAPI

    config = load_app_config()
    config.startup_warnings.extend(request_windows_high_performance_gpu())
    serial_bridge = SerialBridge(baud_rate=config.serial_baud)
    hand_tracker = HandTracker(
        camera_index=config.camera_index,
        width=config.camera_width,
        height=config.camera_height,
        tracking_frame_skip=config.tracking_frame_skip,
        face_detection_enabled=True,
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

    if os.environ.get("AIRTRIXX_LEGACY_TK") == "1":
        import tkinter as tk

        from gui import AirTrixxGUI

        root = tk.Tk()
        app = AirTrixxGUI(root, config, serial_bridge, hand_tracker, servo_controller, fusion_state)
        hand_tracker.start()
        root.mainloop()
        del app
        return

    try:
        import webview
    except Exception as exc:  # pragma: no cover - handled at runtime
        raise SystemExit("pywebview is missing. Run: pip install -r python_app/requirements.txt") from exc

    controller = AirTrixxController(
        config=config,
        serial_bridge=serial_bridge,
        hand_tracker=hand_tracker,
        servo_controller=servo_controller,
        fusion_state=fusion_state,
    )
    api = AirTrixxWebAPI(controller)
    index_path = project_resource_path("python_app", "web", "index.html")
    if not index_path.exists():
        raise SystemExit(f"Embedded web UI is missing: {index_path}")

    controller.start()
    try:
        webview.create_window(
            "AirTrixx",
            index_path.as_uri(),
            js_api=api,
            width=1440,
            height=920,
            min_size=(1120, 720),
        )
        webview.start()
    finally:
        controller.close()


if __name__ == "__main__":
    main()
