from __future__ import annotations

import base64
import copy
import io
import json
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image

from app_paths import AppPaths, build_app_paths_for_root, ensure_app_paths
from appwrite_config import load_appwrite_config
from appwrite_rest import AppwriteCredential, AppwriteError, AppwriteRestClient
from auth_service import AppwriteAuthService, AuthenticatedUser
from config import AppConfig, load_calibration_with_warnings, save_calibration
from fusion_state import FIELD_ORDER, FusionState
from input_backend import PynputInputBackend
from input_mapper import InputMapper, MappingRule, SignalCatalog, load_mapping_config, save_mapping_config
from keyboard_bridge import KeyboardBridge
from mediapipe_tracker import HandTracker
from serial_bridge import SerialBridge
from servo_controller import ServoController
from sync_service import AppwriteSyncService, SyncResult
from wrist_rule_detector import WristReturnRuleDetector


RUNTIME_TICK_S = 1.0 / 60.0
STATE_CACHE_S = 0.08
LOG_LIMIT = 500
DEVICE_LABELS = {
    "antenna": "Antenna",
    "wristband": "Wristband",
    "camdock": "Cam Dock",
    "keyboard": "Keyboard",
    "fans": "Fans",
    "charging_dock": "Charging Dock",
    "camera": "Camera",
    "audiodock": "Audio Dock",
}
DEVICE_IMAGES = {
    "wristband": "components/Wristband.png",
    "camdock": "components/CamDock.png",
    "keyboard": "components/KeyBoardStand.png",
    "fans": "components/Fans.png",
    "charging_dock": "components/Charging.png",
    "audiodock": "components/AudioDock3D.png",
}
METRIC_HISTORY_LIMIT = 48
ADMIN_PAGES = (
    "Dashboard",
    "Signals",
    "Keyboard",
    "Wristband",
    "Wrist Cursor",
    "Visualiser",
    "Wrist Rules",
    "Mappings",
    "Testing",
    "Camera & Servo",
    "Gesture Recorder",
    "Auto Mapper",
    "Audio Dock",
    "Firmware",
    "Settings",
    "Data / Logs",
)
CLIENT_PAGES = ("Dashboard", "Mappings", "Settings")
DUMMY_USERS = {
    "admin": {"password": "admin123", "role": "admin", "name": "Admin", "user_id": "dummy_admin"},
    "client": {"password": "client123", "role": "client", "name": "Client", "user_id": "dummy_client"},
}


class AirTrixxController:
    """UI-independent AirTrixx runtime for the embedded web frontend."""

    def __init__(
        self,
        *,
        config: AppConfig,
        serial_bridge: SerialBridge,
        hand_tracker: HandTracker,
        servo_controller: ServoController,
        fusion_state: FusionState,
    ) -> None:
        self.config = config
        self.serial_bridge = serial_bridge
        self.hand_tracker = hand_tracker
        self.servo_controller = servo_controller
        self.fusion_state = fusion_state
        self.global_paths = build_app_paths_for_root(config.user_data_dir)
        self.active_paths = self.global_paths
        self.appwrite_config = load_appwrite_config()
        self.cloud_client = AppwriteRestClient(self.appwrite_config, timeout_s=8.0)
        self.auth_service = AppwriteAuthService(self.appwrite_config, client=self.cloud_client)
        self.sync_service = AppwriteSyncService(self.appwrite_config, client=self.cloud_client)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.logs: deque[str] = deque(maxlen=LOG_LIMIT)
        self._metric_history: deque[dict[str, Any]] = deque(maxlen=METRIC_HISTORY_LIMIT)
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._cached_state: dict[str, Any] = {}
        self._cached_state_s = 0.0
        self._latest_snapshot: dict[str, Any] = {}
        self._latest_serial_state: dict[str, Any] = {}
        self._latest_tick_error = ""

        self.active_page = "Dashboard"
        self.authenticated = False
        self.auth_user_id = ""
        self.auth_email = ""
        self.auth_user = ""
        self.auth_role = ""
        self.auth_error = ""
        self.auth_session_restored = False
        self.auth_credential: AppwriteCredential | None = None
        self.cloud_sync_status = "Cloud not configured" if not self.appwrite_config.configured else "Not signed in"
        self.cloud_sync_error = ""
        self.cloud_last_synced_at = ""
        self._sync_lock = threading.Lock()
        self._sync_thread: threading.Thread | None = None
        self._sync_pending_reason = ""
        self.camera_enabled = True
        self.auto_tracking_enabled = True
        self.camera_centering_requested = False
        self.fans_requested_on = False
        self.serial_connecting = False
        self.keyboard_training_timer_active = False
        self.keyboard_training_timer_started_s = 0.0
        self.keyboard_training_timer_seconds = 3.0

        self.serial_bridge.on_log = self.log
        self.hand_tracker.on_log = self.log

        self.keyboard_bridge = KeyboardBridge(
            dataset_path=self.config.keyboard_dataset_path,
            model_path=self.config.keyboard_model_path,
            words_path=self.config.keyboard_words_path,
            on_log=self.log,
            on_data_changed=self._on_user_artifact_changed,
        )

        mapping_config, mapping_error = load_mapping_config(self.config.mapping_path)
        self.input_backend = PynputInputBackend()
        self.input_mapper = InputMapper(self.input_backend, mapping_config, on_log=self.log)
        self.mapping_config_path = self.config.mapping_path
        if mapping_error:
            self.log(f"Input mappings reset because config could not be loaded: {mapping_error}")
        if self.input_backend.error:
            self.log(self.input_backend.error)

        self.wrist_rule_detector = WristReturnRuleDetector()
        for warning in self.config.startup_warnings:
            self.log(warning)
        self._restore_auth_session()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self.camera_enabled:
            self.hand_tracker.start()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="AirTrixxRuntime", daemon=True)
        self._thread.start()
        self.log("Embedded web runtime started.")

    def close(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.input_mapper.release_all()
        self.servo_controller.disable_all()
        self.hand_tracker.stop()
        self.keyboard_bridge.disconnect()
        self.serial_bridge.disconnect()
        self.log("AirTrixx runtime stopped.")

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")

    def get_state(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._state_lock:
            if self._cached_state and now - self._cached_state_s < STATE_CACHE_S:
                return copy.deepcopy(self._cached_state)
            state = self._build_state_locked()
            self._cached_state = state
            self._cached_state_s = now
            return copy.deepcopy(state)

    def dispatch(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        try:
            result = self._dispatch(action, payload)
        except Exception as exc:
            self.log(f"Action {action} failed: {type(exc).__name__}: {exc}")
            return {"ok": False, "error": str(exc)}
        with self._state_lock:
            self._cached_state = {}
        return {"ok": True, "result": result}

    def get_camera_frame(self, max_width: int = 960, max_height: int = 540) -> dict[str, Any]:
        if not self.camera_enabled:
            return {"ok": True, "src": None, "reason": "Camera is off."}
        frame = self.hand_tracker.get_latest_frame_rgb()
        if frame is None:
            return {"ok": True, "src": None, "reason": "Waiting for camera frame."}
        image = Image.fromarray(frame)
        image.thumbnail((max(160, int(max_width)), max(120, int(max_height))), Image.Resampling.BILINEAR)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return {"ok": True, "src": f"data:image/jpeg;base64,{encoded}", "reason": ""}

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            started = time.perf_counter()
            try:
                self._tick()
                self._latest_tick_error = ""
            except Exception as exc:
                message = f"Runtime update recovered after error: {type(exc).__name__}: {exc}"
                if message != self._latest_tick_error:
                    self._latest_tick_error = message
                    self.log(message)
            elapsed = time.perf_counter() - started
            self._stop_event.wait(max(0.005, RUNTIME_TICK_S - elapsed))

    def _tick(self) -> None:
        self._drain_log_queue()
        now_s = time.monotonic()
        serial_state = self._serial_state_with_keyboard_overlay(self.serial_bridge.get_latest_state(), now_s)
        hands = self.hand_tracker.get_latest_hands() if self.camera_enabled else {}

        if self.serial_bridge.is_connected and self.auto_tracking_enabled:
            self.servo_controller.send_for_hands(hands, serial_state)
        if self.camera_centering_requested and self.serial_bridge.is_connected:
            if self.servo_controller.center_camera():
                self.camera_centering_requested = False
                self.log("Camera center command sent.")

        wrist_rule_event = self.wrist_rule_detector.process_serial_state(serial_state, now_s=now_s)
        wrist_rule_output = self.wrist_rule_detector.output(now_s)
        snapshot = self.fusion_state.build_snapshot(
            serial_state,
            hands,
            now_s=now_s,
            model_value="none",
            wrist_rule_value=str(wrist_rule_output["value"]),
            wrist_rotate_left_return=bool(wrist_rule_output["rotate_left_return"]),
            wrist_rotate_right_return=bool(wrist_rule_output["rotate_right_return"]),
            base_z=self._calibration_base_z(),
        )
        snapshot["face_state"] = self.hand_tracker.get_latest_face() if self.camera_enabled else {}
        snapshot["_signal_sequence"] = self._mapping_signal_sequence(snapshot)
        if wrist_rule_event:
            self.log(f"Wrist rule event: {wrist_rule_event}")

        if self.keyboard_training_timer_active:
            self._update_keyboard_training_timer(now_s)
        self.keyboard_bridge.tick(now_s=now_s)
        if self.serial_bridge.is_connected or self.keyboard_bridge.source_ready:
            self.input_mapper.process(snapshot, now_s, suppress_output=False)
        else:
            self.input_mapper.release_all()

        with self._state_lock:
            self._latest_serial_state = serial_state
            self._latest_snapshot = snapshot

    def _dispatch(self, action: str, payload: dict[str, Any]) -> Any:
        if action == "auth.login":
            return self._login(payload)
        if action == "auth.logout":
            self._logout()
            return True
        if not self.authenticated:
            return {"error": "Login required."}
        if not self._action_allowed_for_role(action):
            self.log(f"Blocked {action} for {self.auth_role} role.")
            return {"error": "Action is not available for this role."}
        if action == "nav.set":
            requested_page = str(payload.get("page") or "Dashboard")
            self.active_page = requested_page if requested_page in self._allowed_pages() else self._allowed_pages()[0]
            return self.active_page
        if action == "serial.refresh":
            return self._serial_ports()
        if action == "serial.connect":
            port = str(payload.get("port") or "").strip() or None
            self._start_serial_connect(port)
            return True
        if action == "serial.disconnect":
            self.serial_bridge.disconnect()
            return True
        if action == "camera.toggle_power":
            self.camera_enabled = not self.camera_enabled
            if self.camera_enabled:
                self.hand_tracker.start()
                self.log("Camera enabled.")
            else:
                self.hand_tracker.stop()
                self.log("Camera disabled and released.")
            return self.camera_enabled
        if action == "camera.toggle_mirror":
            mirrored = not bool(getattr(self.hand_tracker, "mirror_preview", False))
            self.hand_tracker.configure(mirror_preview=mirrored)
            self.log(f"Camera mirroring {'enabled' if mirrored else 'disabled'}.")
            return mirrored
        if action == "camera.center":
            self.camera_centering_requested = True
            self.log("Camera centering requested.")
            return True
        if action == "tracking.toggle":
            self.auto_tracking_enabled = not self.auto_tracking_enabled
            if not self.auto_tracking_enabled:
                self.servo_controller.disable_all()
            self.log(f"Auto tracking {'enabled' if self.auto_tracking_enabled else 'disabled'}.")
            return self.auto_tracking_enabled
        if action == "fans.toggle":
            return self._toggle_fans()
        if action == "keyboard.toggle_live":
            enabled = not bool(self.keyboard_bridge.live_prediction_enabled)
            self.keyboard_bridge.set_live_prediction_enabled(enabled)
            return enabled
        if action == "keyboard.calibrate":
            return self.keyboard_bridge.reset_for_calibration()
        if action == "keyboard.start_training":
            words = self._words_from_payload(payload)
            repetitions = max(1, int(float(payload.get("repetitions", 3) or 3)))
            include_commands = bool(payload.get("include_commands", True))
            reset_dataset = bool(payload.get("reset_dataset", False))
            return self.keyboard_bridge.start_training(
                words,
                repetitions=repetitions,
                include_command_words=include_commands,
                reset_dataset=reset_dataset,
            )
        if action == "keyboard.record_next":
            return self.keyboard_bridge.arm_next_training_sample()
        if action == "keyboard.start_timer":
            seconds = max(1.0, float(payload.get("seconds", 3) or 3))
            self.keyboard_training_timer_seconds = seconds
            self.keyboard_training_timer_started_s = time.monotonic()
            self.keyboard_training_timer_active = True
            self.log(f"Keyboard timer started for {seconds:g}s.")
            return True
        if action == "keyboard.stop_timer":
            self.keyboard_training_timer_active = False
            return self.keyboard_bridge.disarm_training_sample(requeue=True)
        if action == "keyboard.train_model":
            return self.keyboard_bridge.train_model_async()
        if action == "keyboard.cancel_training":
            self.keyboard_training_timer_active = False
            self.keyboard_bridge.cancel_training()
            return True
        if action == "mapping.toggle":
            self.input_mapper.set_enabled(not self.input_mapper.enabled)
            self.log(f"Input mapper {'armed' if self.input_mapper.enabled else 'disabled'}.")
            return self.input_mapper.enabled
        if action == "mapping.set_profile":
            profile = str(payload.get("profile") or "")
            changed = self.input_mapper.set_active_profile(profile)
            if changed:
                save_mapping_config(self.input_mapper.config, self.mapping_config_path)
                self.log(f"Active mapping profile: {profile}")
                self._queue_cloud_sync("mapping profile changed")
            return changed
        if action == "mapping.save":
            save_mapping_config(self.input_mapper.config, self.mapping_config_path)
            self.log("Input mappings saved.")
            self._queue_cloud_sync("mapping saved")
            return True
        if action == "mapping.rule.upsert":
            changed = self._upsert_mapping_rule(payload.get("rule") or {})
            if changed:
                self._queue_cloud_sync("mapping rule saved")
            return changed
        if action == "mapping.rule.delete":
            changed = self._delete_mapping_rule(str(payload.get("id") or ""))
            if changed:
                self._queue_cloud_sync("mapping rule deleted")
            return changed
        if action == "mapping.rule.toggle":
            enabled = payload.get("enabled")
            enabled_value = None if enabled is None else bool(enabled)
            changed = self._toggle_mapping_rule(str(payload.get("id") or ""), enabled_value)
            if changed:
                self._queue_cloud_sync("mapping rule toggled")
            return changed
        if action == "sync.now":
            return self._sync_now("manual sync").__dict__
        if action == "logs.clear":
            self.logs.clear()
            return True
        if action == "app.open_data_dir":
            return self._open_path(self.config.user_data_dir)
        return False

    def _start_serial_connect(self, port: str | None) -> None:
        if self.serial_connecting:
            return

        def worker() -> None:
            self.serial_connecting = True
            try:
                self.serial_bridge.connect(port)
            finally:
                self.serial_connecting = False

        threading.Thread(target=worker, name="AirTrixxSerialConnect", daemon=True).start()

    def _toggle_fans(self) -> bool:
        if not self.serial_bridge.is_connected:
            self.log("Connect to the Antenna serial port before controlling fans.")
            return False
        fans = self._fan_device_state()
        current_on = fans.get("fan_on")
        desired_on = (not current_on) if isinstance(current_on, bool) else (not self.fans_requested_on)
        command = {"cmd": "fans", "target": "fans", "fan_on": desired_on}
        if self.serial_bridge.send_command(command):
            self.fans_requested_on = desired_on
            self.log(f"Sent fan {'on' if desired_on else 'off'} command.")
            return True
        self.log("Failed to send fan command to Antenna.")
        return False

    def _update_keyboard_training_timer(self, now_s: float) -> None:
        elapsed = now_s - self.keyboard_training_timer_started_s
        if elapsed < self.keyboard_training_timer_seconds:
            return
        self.keyboard_training_timer_active = False
        if self.keyboard_bridge.arm_next_training_sample():
            self.log("Keyboard timer armed the next sample.")

    def _serial_state_with_keyboard_overlay(self, serial_state: dict[str, Any], now_s: float) -> dict[str, Any]:
        state = copy.deepcopy(serial_state) if isinstance(serial_state, dict) else {}
        devices = state.setdefault("devices", {})
        if not isinstance(devices, dict):
            devices = {}
            state["devices"] = devices
        keyboard_device = devices.get("keyboard")
        self.keyboard_bridge.ingest_antenna_device(keyboard_device if isinstance(keyboard_device, dict) else None, now_s=now_s)
        devices["keyboard"] = self.keyboard_bridge.snapshot()
        return state

    def _build_state_locked(self) -> dict[str, Any]:
        serial_state = copy.deepcopy(self._latest_serial_state)
        snapshot = copy.deepcopy(self._latest_snapshot)
        devices = serial_state.get("devices", {}) if isinstance(serial_state, dict) else {}
        devices = devices if isinstance(devices, dict) else {}
        if self.active_page not in self._allowed_pages():
            self.active_page = self._allowed_pages()[0]
        signals = [
            {
                "id": signal.id,
                "group": signal.group,
                "label": signal.label,
                "value": signal.display_value,
            }
            for signal in SignalCatalog.rows(snapshot)[:240]
        ]
        keyboard_state = self.keyboard_bridge.snapshot()
        keyboard_state["live_prediction_enabled"] = bool(self.keyboard_bridge.live_prediction_enabled)
        device_cards = self._device_cards(devices)
        fan_state = self._fan_state(devices)
        mapping_state = self._mapping_state(signals)
        self._record_metric_sample(fan_state)
        return {
            "app": {
                "name": "AirTrixx",
                "activePage": self.active_page,
                "navPages": list(self._allowed_pages()),
                "userDataDir": str(self.config.user_data_dir),
                "runtime": "embedded-web",
            },
            "auth": {
                "authenticated": self.authenticated,
                "userId": self.auth_user_id,
                "email": self.auth_email,
                "user": self.auth_user,
                "displayName": self.auth_user,
                "role": self.auth_role,
                "error": self.auth_error,
                "sessionRestored": self.auth_session_restored,
                "loginHint": "Dummy users: admin/admin123 or client/client123",
            },
            "cloud": {
                "configured": self.appwrite_config.configured,
                "syncStatus": self.cloud_sync_status,
                "lastSyncedAt": self.cloud_last_synced_at,
                "error": self.cloud_sync_error,
            },
            "status": self._status_chips(),
            "serial": {
                "connected": self.serial_bridge.is_connected,
                "connecting": self.serial_connecting,
                "port": self.serial_bridge.current_port,
                "ports": self._serial_ports(),
                "sequence": serial_state.get("sequence"),
                "t_ms": serial_state.get("t_ms"),
            },
            "devices": device_cards,
            "camera": {
                "enabled": self.camera_enabled,
                "mirror": bool(getattr(self.hand_tracker, "mirror_preview", False)),
                "hasFrame": self.hand_tracker.has_latest_frame() if self.camera_enabled else False,
                "face": snapshot.get("face_state", {}),
                "autoTracking": self.auto_tracking_enabled,
            },
            "fans": fan_state,
            "keyboard": keyboard_state,
            "mappings": mapping_state,
            "signals": signals,
            "analytics": self._analytics(device_cards, fan_state, mapping_state, signals),
            "raw": {
                "serial": self._json_text(serial_state),
                "snapshot": self._json_text(
                    {
                        "field_order": FIELD_ORDER,
                        "input_array": snapshot.get("input_array", []),
                        "input_dict": snapshot.get("input_dict", {}),
                    }
                ),
                "servo": self._json_text(self.servo_controller.last_debug_snapshot),
            },
            "logs": list(self.logs)[-260:],
        }

    def _login(self, payload: dict[str, Any]) -> dict[str, Any]:
        email = str(payload.get("email") or payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        dummy = self._dummy_user(email, password)
        if dummy is not None:
            self._activate_dummy_user(dummy)
            return {"authenticated": True, "role": self.auth_role, "user": self.auth_user, "email": self.auth_email}
        try:
            user = self.auth_service.login(email, password)
        except AppwriteError as exc:
            self.authenticated = False
            self.auth_user_id = ""
            self.auth_email = ""
            self.auth_user = ""
            self.auth_role = ""
            self.auth_credential = None
            self.auth_error = str(exc)
            self.cloud_sync_status = "Sign in failed"
            self.cloud_sync_error = str(exc)
            self.log(f"Failed Appwrite login for {email or 'blank email'}: {exc}")
            return {"authenticated": False, "error": self.auth_error}
        self._activate_authenticated_user(user)
        return {"authenticated": True, "role": self.auth_role, "user": self.auth_user, "email": self.auth_email}

    @staticmethod
    def _dummy_user(username: str, password: str) -> dict[str, str] | None:
        normalized = username.strip().lower()
        if "@" in normalized:
            normalized = normalized.split("@", 1)[0]
        user = DUMMY_USERS.get(normalized)
        if not user or password != user["password"]:
            return None
        return user

    def _activate_dummy_user(self, user: dict[str, str]) -> None:
        self.authenticated = True
        self.auth_user_id = user["user_id"]
        self.auth_email = ""
        self.auth_user = user["name"]
        self.auth_role = user["role"]
        self.auth_error = ""
        self.auth_session_restored = False
        self.auth_credential = None
        self.active_page = self._allowed_pages()[0]
        self.cloud_sync_status = "Local dummy session"
        self.cloud_sync_error = ""
        self._switch_to_user_data(user["user_id"])
        self.log(f"{self.auth_user} signed in as {self.auth_role} using dummy login.")

    def _restore_auth_session(self) -> None:
        if not self.appwrite_config.configured:
            self.log("Appwrite is not configured; set APPWRITE_PROJECT_ID to enable cloud login.")
            return
        try:
            user = self.auth_service.restore_session()
        except AppwriteError as exc:
            self.cloud_sync_status = "Session restore failed"
            self.cloud_sync_error = str(exc)
            self.log(f"Could not restore Appwrite session: {exc}")
            return
        if user is not None:
            self._activate_authenticated_user(user)

    def _activate_authenticated_user(self, user: AuthenticatedUser) -> None:
        self.authenticated = True
        self.auth_user_id = user.user_id
        self.auth_email = user.email
        self.auth_user = user.display_name
        self.auth_role = user.role
        self.auth_error = ""
        self.auth_session_restored = user.session_restored
        self.auth_credential = user.credential
        self.active_page = self._allowed_pages()[0]
        self.log(f"{self.auth_user} signed in as {self.auth_role}.")
        self._switch_to_user_data(user.user_id)
        result = self._sync_on_login()
        if result.changed and result.action == "download":
            self._reload_user_artifacts()

    def _logout(self) -> None:
        credential = self.auth_credential
        self.auth_service.logout(credential)
        self.authenticated = False
        self.auth_user_id = ""
        self.auth_email = ""
        self.auth_user = ""
        self.auth_role = ""
        self.auth_error = ""
        self.auth_session_restored = False
        self.auth_credential = None
        self.active_page = "Dashboard"
        self.input_mapper.release_all()
        self.cloud_sync_status = "Not signed in" if self.appwrite_config.configured else "Cloud not configured"
        self.cloud_sync_error = ""
        self.log("Signed out.")

    def _switch_to_user_data(self, user_id: str) -> None:
        safe_user_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in user_id) or "unknown"
        paths = build_app_paths_for_root(self.global_paths.user_data_dir / "users" / safe_user_id)
        ensure_app_paths(paths)
        self.sync_service.seed_user_from_legacy(self.global_paths, paths)
        self.active_paths = paths
        self._apply_paths(paths)

    def _apply_paths(self, paths: AppPaths) -> None:
        self.config.user_data_dir = paths.user_data_dir
        self.config.config_dir = paths.config_dir
        self.config.logs_dir = paths.logs_dir
        self.config.temp_dir = paths.temp_dir
        self.config.exports_dir = paths.exports_dir
        self.config.calibration_path = paths.calibration_path
        self.config.mapping_path = paths.mapping_path
        self.config.gesture_data_dir = paths.gesture_data_dir
        self.config.keyboard_data_dir = paths.keyboard_data_dir
        self.config.wristband_data_dir = paths.wristband_data_dir
        self.config.wristband_model_dir = paths.wristband_model_dir
        self.config.audio_training_dir = paths.audio_training_dir
        self.config.servo_debug_log_path = paths.servo_debug_log_path
        self.config.audio_recording_path = paths.audio_recording_path
        self.config.keyboard_dataset_path = paths.keyboard_dataset_path
        self.config.keyboard_model_path = paths.keyboard_model_path
        self.config.keyboard_words_path = paths.keyboard_words_path
        self.config.wristband_model_path = paths.wristband_model_path
        self.config.wristband_labels_path = paths.wristband_labels_path
        self._reload_user_artifacts()

    def _reload_user_artifacts(self) -> None:
        calibration, warnings = load_calibration_with_warnings(self.config.calibration_path)
        self.config.calibration = calibration
        self.servo_controller.update_calibration(calibration)
        for warning in warnings:
            self.log(warning)
        mapping_config, mapping_error = load_mapping_config(self.config.mapping_path)
        self.input_mapper.config = mapping_config
        self.mapping_config_path = self.config.mapping_path
        if mapping_error:
            self.log(f"Input mappings reset because config could not be loaded: {mapping_error}")
        self.keyboard_bridge.set_paths(
            dataset_path=self.config.keyboard_dataset_path,
            model_path=self.config.keyboard_model_path,
            words_path=self.config.keyboard_words_path,
        )

    def _sync_on_login(self) -> SyncResult:
        if not self.auth_credential or not self.auth_user_id:
            return SyncResult(False, "idle", "Not signed in.")
        self.cloud_sync_status = "Syncing..."
        self.cloud_sync_error = ""
        result = self.sync_service.sync_on_login(
            user_id=self.auth_user_id,
            credential=self.auth_credential,
            paths=self.active_paths,
        )
        self._record_sync_result(result)
        return result

    def _sync_now(self, reason: str) -> SyncResult:
        if not self.auth_credential or not self.auth_user_id:
            result = SyncResult(False, "error", "Login required.", error="Login required.")
            self._record_sync_result(result)
            return result
        self.cloud_sync_status = "Syncing..."
        self.cloud_sync_error = ""
        try:
            result = self.sync_service.upload(
                user_id=self.auth_user_id,
                credential=self.auth_credential,
                paths=self.active_paths,
                reason=reason,
            )
        except Exception as exc:
            result = SyncResult(False, "error", "Cloud sync failed.", error=str(exc))
        self._record_sync_result(result)
        return result

    def _queue_cloud_sync(self, reason: str) -> None:
        if not self.authenticated or not self.auth_credential:
            return
        with self._sync_lock:
            if self._sync_thread and self._sync_thread.is_alive():
                self._sync_pending_reason = reason
                self.cloud_sync_status = "Sync queued"
                return
            self._sync_thread = threading.Thread(target=self._sync_worker, args=(reason,), name="AirTrixxCloudSync", daemon=True)
            self._sync_thread.start()

    def _sync_worker(self, reason: str) -> None:
        current_reason = reason
        while current_reason:
            self._sync_now(current_reason)
            with self._sync_lock:
                current_reason = self._sync_pending_reason
                self._sync_pending_reason = ""
                if not current_reason:
                    self._sync_thread = None
                    return

    def _record_sync_result(self, result: SyncResult) -> None:
        if result.error:
            self.cloud_sync_status = result.error
            self.cloud_sync_error = result.error
            self.log(f"Cloud sync failed: {result.error}")
            return
        self.cloud_sync_status = result.message
        self.cloud_sync_error = ""
        if result.last_synced_at:
            self.cloud_last_synced_at = result.last_synced_at
        self.log(result.message)

    def _on_user_artifact_changed(self, reason: str) -> None:
        self._queue_cloud_sync(reason)

    def _allowed_pages(self) -> tuple[str, ...]:
        if self.auth_role == "client":
            return CLIENT_PAGES
        if self.auth_role == "admin":
            return ADMIN_PAGES
        return CLIENT_PAGES

    def _action_allowed_for_role(self, action: str) -> bool:
        if self.auth_role == "admin":
            return True
        if self.auth_role != "client":
            return False
        allowed_exact = {
            "nav.set",
            "serial.refresh",
            "serial.connect",
            "serial.disconnect",
            "camera.toggle_power",
            "camera.center",
            "tracking.toggle",
            "fans.toggle",
            "mapping.toggle",
            "mapping.set_profile",
            "mapping.save",
            "mapping.rule.upsert",
            "mapping.rule.delete",
            "mapping.rule.toggle",
            "sync.now",
            "app.open_data_dir",
        }
        return action in allowed_exact

    def _status_chips(self) -> list[dict[str, str]]:
        mapper = "armed" if self.input_mapper.enabled else "disabled"
        camera = "live" if self.camera_enabled and self.hand_tracker.has_latest_frame() else "off" if not self.camera_enabled else "no frame"
        return [
            {"label": "Hub", "value": self.serial_bridge.current_port or "disconnected", "tone": "ok" if self.serial_bridge.is_connected else "warn"},
            {"label": "Mapper", "value": mapper, "tone": "ok" if self.input_mapper.enabled else "warn"},
            {"label": "Camera", "value": camera, "tone": "ok" if camera == "live" else "warn"},
        ]

    def _device_cards(self, devices: dict[str, Any]) -> list[dict[str, Any]]:
        cards = []
        for key, label in DEVICE_LABELS.items():
            device = devices.get(key, {}) if key != "antenna" else {}
            if key == "antenna":
                status = "ok" if self.serial_bridge.is_connected else "disconnected"
                detail = self.serial_bridge.current_port or "No USB link"
                battery = None
            elif key == "camera":
                status = "ok" if self.camera_enabled else "off"
                detail = "Live frame" if self.hand_tracker.has_latest_frame() else "Waiting for frame"
                battery = None
            elif isinstance(device, dict):
                status = str(device.get("status") or "unknown")
                detail = self._device_detail(key, device)
                battery = self._battery_level(device)
            else:
                status = "unknown"
                detail = "-"
                battery = None
            cards.append(
                {
                    "key": key,
                    "label": label,
                    "status": status,
                    "detail": detail,
                    "battery": battery,
                    "tone": self._status_tone(status, battery),
                    **({"image": DEVICE_IMAGES[key]} if key in DEVICE_IMAGES else {}),
                }
            )
        return cards

    def _record_metric_sample(self, fan_state: dict[str, Any]) -> None:
        camera_live = self.camera_enabled and self.hand_tracker.has_latest_frame()
        self._metric_history.append(
            {
                "hub": 1 if self.serial_bridge.is_connected else 0,
                "mapper": 1 if self.input_mapper.enabled else 0,
                "camera": 1 if camera_live else 0,
                "temp1": fan_state.get("temp1"),
                "temp2": fan_state.get("temp2"),
            }
        )

    def _analytics(
        self,
        device_cards: list[dict[str, Any]],
        fan_state: dict[str, Any],
        mapping_state: dict[str, Any],
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        battery_levels = [
            {"key": card["key"], "label": card["label"], "value": card.get("battery")}
            for card in device_cards
            if card.get("image")
        ]
        group_counts: dict[str, int] = {}
        for signal in signals:
            group = str(signal.get("group") or "Other")
            group_counts[group] = group_counts.get(group, 0) + 1
        signal_groups = [{"group": group, "count": count} for group, count in sorted(group_counts.items())]
        rules = mapping_state.get("rules") or []
        enabled_rules = sum(1 for rule in rules if rule.get("enabled"))
        return {
            "batteryLevels": battery_levels,
            "temperatures": {"temp1": fan_state.get("temp1"), "temp2": fan_state.get("temp2")},
            "signalGroups": signal_groups,
            "mapping": {
                "total": len(rules),
                "enabled": enabled_rules,
                "armed": bool(mapping_state.get("enabled")),
            },
            "timeline": list(self._metric_history),
        }

    def _fan_state(self, devices: dict[str, Any]) -> dict[str, Any]:
        fans = devices.get("fans", {}) if isinstance(devices, dict) else {}
        fans = fans if isinstance(fans, dict) else {}
        temps = fans.get("temps", {}) if isinstance(fans.get("temps"), dict) else {}
        fan_on = fans.get("fan_on")
        if isinstance(fan_on, bool):
            self.fans_requested_on = fan_on
        return {
            "status": str(fans.get("status", "not_connected")),
            "fanOn": fan_on if isinstance(fan_on, bool) else None,
            "requestedOn": self.fans_requested_on,
            "temp1": temps.get("sensor_1_c"),
            "temp2": temps.get("sensor_2_c"),
            "battery": self._battery_level(fans),
        }

    def _mapping_state(self, signals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        config = self.input_mapper.config
        debug_rules = self.input_mapper.debug_snapshot().get("rules", {})
        rules = []
        sources = {"keyboard.input"}
        for rule in self.input_mapper.active_rules():
            if rule.source:
                sources.add(rule.source)
            rules.append(
                {
                    "id": rule.id,
                    "name": rule.name,
                    "enabled": rule.enabled,
                    "source": rule.source,
                    "condition": rule.condition_summary(),
                    "action": rule.action.summary(),
                    "status": debug_rules.get(rule.id, {}).get("status", "idle"),
                    "rule": rule.to_dict(),
                }
            )
        if signals:
            for signal in signals:
                signal_id = str(signal.get("id") or "")
                if signal_id and not signal_id.startswith("fused."):
                    sources.add(signal_id)
        return {
            "enabled": self.input_mapper.enabled,
            "status": self.input_mapper.last_status,
            "activeProfile": config.active_profile,
            "profiles": config.profile_names(),
            "sources": sorted(sources),
            "rules": rules,
        }

    def _upsert_mapping_rule(self, rule_data: dict[str, Any]) -> bool:
        try:
            rule = MappingRule.from_dict(rule_data)
        except ValueError as exc:
            self.log(f"Mapping rule invalid: {exc}")
            return False
        self.input_mapper.release_rule(rule.id)
        profile = self.input_mapper.config.active()
        for index, existing in enumerate(profile.mappings):
            if existing.id == rule.id:
                profile.mappings[index] = rule
                break
        else:
            profile.mappings.append(rule)
        save_mapping_config(self.input_mapper.config, self.mapping_config_path)
        self.log(f"Mapping rule saved: {rule.name}")
        return True

    def _delete_mapping_rule(self, rule_id: str) -> bool:
        if not rule_id:
            return False
        profile = self.input_mapper.config.active()
        before = len(profile.mappings)
        self.input_mapper.release_rule(rule_id)
        profile.mappings = [item for item in profile.mappings if item.id != rule_id]
        if len(profile.mappings) == before:
            return False
        save_mapping_config(self.input_mapper.config, self.mapping_config_path)
        self.log(f"Deleted mapping rule: {rule_id}")
        return True

    def _toggle_mapping_rule(self, rule_id: str, enabled: bool | None) -> bool:
        if not rule_id:
            return False
        profile = self.input_mapper.config.active()
        for rule in profile.mappings:
            if rule.id == rule_id:
                rule.enabled = not rule.enabled if enabled is None else bool(enabled)
                if not rule.enabled:
                    self.input_mapper.release_rule(rule.id)
                save_mapping_config(self.input_mapper.config, self.mapping_config_path)
                state = "enabled" if rule.enabled else "disabled"
                self.log(f"Mapping rule {rule.name} {state}.")
                return True
        return False

    def _fan_device_state(self) -> dict[str, Any]:
        state = self.serial_bridge.get_latest_state()
        devices = state.get("devices", {}) if isinstance(state, dict) else {}
        fans = devices.get("fans", {}) if isinstance(devices, dict) else {}
        return fans if isinstance(fans, dict) else {}

    def _drain_log_queue(self) -> None:
        while True:
            try:
                self.logs.append(self.log_queue.get_nowait())
            except queue.Empty:
                break

    def _serial_ports(self) -> list[dict[str, str]]:
        return SerialBridge.available_ports()

    @staticmethod
    def _words_from_payload(payload: dict[str, Any]) -> list[str]:
        words_value = payload.get("words", "")
        if isinstance(words_value, list):
            return [str(word).strip() for word in words_value if str(word).strip()]
        return [part.strip() for part in str(words_value).replace("\n", ",").split(",") if part.strip()]

    @staticmethod
    def _json_text(value: Any) -> str:
        try:
            return json.dumps(value, indent=2, default=str)
        except TypeError:
            return str(value)

    @staticmethod
    def _battery_level(device: dict[str, Any]) -> float | None:
        battery = device.get("battery")
        if isinstance(battery, dict):
            value = battery.get("percent")
        else:
            value = device.get("battery_level")
        if isinstance(value, bool) or value is None:
            return None
        try:
            return max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _status_tone(status: str, battery: float | None = None) -> str:
        normalized = status.strip().lower().replace("_", " ")
        if normalized in {"ok", "connected", "live"} and (battery is None or battery > 25):
            return "ok"
        if normalized in {"off", "unknown", "waiting", "tbd"}:
            return "warn"
        if battery is not None and battery <= 25:
            return "danger"
        if normalized in {"not connected", "disconnected", "offline"}:
            return "danger"
        return "warn"

    @staticmethod
    def _device_detail(device: str, payload: dict[str, Any]) -> str:
        if device == "camdock":
            tof = payload.get("tof", {})
            if isinstance(tof, dict):
                return f"L {tof.get('left_mm', '-')} mm, R {tof.get('right_mm', '-')} mm"
        if device == "wristband":
            return f"pitch {payload.get('pitch', '-')}, roll {payload.get('roll', '-')}"
        if device == "keyboard":
            word = payload.get("predicted_word") or payload.get("input") or "-"
            confidence = payload.get("prediction_confidence")
            if isinstance(confidence, (float, int)):
                return f"{word} ({confidence:.2f})"
            return str(word)
        if device == "fans":
            return "on" if payload.get("fan_on") is True else "off" if payload.get("fan_on") is False else "unknown"
        return str(payload.get("input", "-"))

    def _calibration_base_z(self) -> float | None:
        session = self.config.calibration.get("session_calibration", {})
        if not isinstance(session, dict):
            return None
        distances = [
            entry.get("distance_mm")
            for entry in session.values()
            if isinstance(entry, dict) and isinstance(entry.get("distance_mm"), (int, float))
        ]
        if not distances:
            return None
        return float(sum(distances) / len(distances))

    @staticmethod
    def _mapping_signal_sequence(snapshot: dict[str, Any]) -> tuple[Any, ...]:
        raw = snapshot.get("raw_device_state", {}) if isinstance(snapshot, dict) else {}
        devices = raw.get("devices", {}) if isinstance(raw, dict) else {}
        parts: list[Any] = [raw.get("sequence"), raw.get("t_ms")]
        if isinstance(devices, dict):
            for key in sorted(devices):
                device = devices.get(key)
                if isinstance(device, dict):
                    parts.append((key, device.get("sequence"), device.get("t_ms")))
        return tuple(parts)

    @staticmethod
    def _open_path(path: Path) -> bool:
        import os
        import platform
        import subprocess

        try:
            if platform.system() == "Windows":
                os.startfile(path)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return True
        except Exception:
            return False

    def save_current_calibration(self) -> bool:
        save_calibration(self.config.calibration, self.config.calibration_path)
        self._queue_cloud_sync("calibration saved")
        return True
