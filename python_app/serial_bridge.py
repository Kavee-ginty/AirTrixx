from __future__ import annotations

import copy
import json
import queue
import threading
import time
from collections import deque
from typing import Any, Callable

try:
    import serial
    from serial.tools import list_ports
except Exception:  # pragma: no cover - handled at runtime for missing dependency
    serial = None
    list_ports = None


LogCallback = Callable[[str], None]
WRISTBAND_SAMPLE_STALE_S = 1.5
DEVICE_DELTA_STALE_S = 1.5
DISCONNECTED_STATUSES = {"not_connected", "disconnected", "tbd"}
DEVICE_LIVE_FIELDS = {
    "wristband": ("accel", "gyro", "calibrated_accel", "pitch", "roll", "yaw"),
    "keyboard": ("tof", "valid", "input"),
    "camdock": ("tof", "active_target"),
    "fans": ("input", "fan_on"),
    "charging_dock": ("input", "active_tab", "priority_channel"),
    "audiodock": ("input", "clap_detected", "clap_type"),
}


class SerialBridge:
    def __init__(
        self,
        baud_rate: int = 921600,
        on_log: LogCallback | None = None,
        on_state: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.baud_rate = baud_rate
        self.on_log = on_log
        self.on_state = on_state
        self._serial = None
        self._serial_lock = threading.RLock()
        self._latest_lock = threading.Lock()
        self._latest_state: dict[str, Any] = {}
        self._wristband_states: deque[dict[str, Any]] = deque(maxlen=512)
        self._wristband_last_sample_s: float | None = None
        self._device_last_received_s: dict[str, float] = {}
        self._device_sequences: dict[str, int] = {}
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._manual_disconnect = False
        self._current_port: str | None = None
        self.audio_dock_bridge = None
        self._write_queue: queue.Queue[tuple[str, str | None]] = queue.Queue(maxsize=512)
        self._coalesced_writes: dict[str, str] = {}
        self._queued_coalesce_keys: set[str] = set()
        self._coalesced_lock = threading.Lock()
        self._writer_thread = threading.Thread(target=self._write_loop, daemon=True)
        self._writer_thread.start()

    @staticmethod
    def available_ports() -> list[dict[str, str]]:
        if list_ports is None:
            return []
        ports = []
        for port in list_ports.comports():
            ports.append(
                {
                    "device": port.device,
                    "description": port.description or "",
                    "hwid": port.hwid or "",
                }
            )
        return ports

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)

    def connect(self, port: str | None = None) -> bool:
        if serial is None:
            self._log("pyserial is not installed. Run pip install -r requirements.txt.")
            return False

        if self.is_connected:
            return True

        self._manual_disconnect = False
        candidates = [port] if port else [p["device"] for p in self.available_ports()]
        candidates = [p for p in candidates if p]
        if not candidates:
            self._log("No COM ports found.")
            return False

        for candidate in candidates:
            if self._open_port(candidate):
                self._current_port = candidate
                self._start_reader()
                self._log(f"Connected to {candidate} at {self.baud_rate} baud.")
                return True

        self._log("Could not connect to any candidate COM port.")
        return False

    def disconnect(self) -> None:
        self._manual_disconnect = True
        self._stop_event.set()
        self._close_serial()
        self._clear_write_queue()
        thread = self._reader_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        with self._latest_lock:
            self._latest_state = {}
            self._wristband_states.clear()
            self._wristband_last_sample_s = None
            self._device_last_received_s.clear()
            self._device_sequences.clear()
        self._current_port = None
        self._log("Serial disconnected.")

    @property
    def is_connected(self) -> bool:
        with self._serial_lock:
            return bool(self._serial and self._serial.is_open)

    @property
    def current_port(self) -> str | None:
        return self._current_port

    def get_latest_state(self) -> dict[str, Any]:
        with self._latest_lock:
            self._expire_stale_devices_locked()
            return copy.deepcopy(self._latest_state)

    def drain_wristband_states(self) -> list[dict[str, Any]]:
        with self._latest_lock:
            self._expire_stale_devices_locked()
            states = list(self._wristband_states)
            self._wristband_states.clear()
        return states

    def _expire_stale_devices_locked(self) -> None:
        now_s = time.monotonic()
        for device_name, received_s in list(self._device_last_received_s.items()):
            if now_s - received_s <= DEVICE_DELTA_STALE_S:
                continue
            self._mark_device_disconnected_locked(device_name)
        if self._wristband_last_sample_s is not None and now_s - self._wristband_last_sample_s > WRISTBAND_SAMPLE_STALE_S:
            self._mark_wristband_disconnected_locked()

    def _mark_device_disconnected_locked(self, device_name: str) -> None:
        devices = self._latest_state.get("devices")
        device = devices.get(device_name) if isinstance(devices, dict) else None
        if isinstance(device, dict):
            device["status"] = "not_connected"
            device["sequence"] = None
            device["t_ms"] = None
            for field in DEVICE_LIVE_FIELDS.get(device_name, ()):
                value = device.get(field)
                if isinstance(value, dict):
                    device[field] = {key: None for key in value}
                elif isinstance(value, bool):
                    device[field] = False
                else:
                    device[field] = None
        self._device_last_received_s.pop(device_name, None)
        self._device_sequences.pop(device_name, None)
        if device_name == "wristband":
            self._wristband_states.clear()
            self._wristband_last_sample_s = None

    def _mark_wristband_disconnected_locked(self) -> None:
        devices = self._latest_state.get("devices")
        wristband = devices.get("wristband") if isinstance(devices, dict) else None
        if isinstance(wristband, dict):
            wristband["status"] = "not_connected"
            wristband["sequence"] = None
            wristband["t_ms"] = None
            wristband["accel"] = {"x": None, "y": None, "z": None}
            wristband["gyro"] = {"x": None, "y": None, "z": None}
            wristband["pitch"] = None
            wristband["roll"] = None
            wristband["yaw"] = None
        self._wristband_states.clear()
        self._wristband_last_sample_s = None

    @staticmethod
    def _sequence_is_newer(sequence: int, previous: int) -> bool:
        difference = (sequence - previous) & 0xFFFF
        return 0 < difference < 0x8000

    @classmethod
    def _merge_dict(cls, target: dict[str, Any], update: dict[str, Any]) -> None:
        for key, value in update.items():
            existing = target.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                cls._merge_dict(existing, value)
            else:
                target[key] = copy.deepcopy(value)

    def _store_device_delta_locked(self, delta: dict[str, Any]) -> dict[str, Any]:
        device_name = str(delta.get("device", "")).strip().lower()
        fields = delta.get("fields")
        sequence = delta.get("sequence")
        if not device_name or not isinstance(fields, dict) or not isinstance(sequence, int):
            return self._latest_state
        previous = self._device_sequences.get(device_name)
        if previous is not None and sequence != previous and not self._sequence_is_newer(sequence, previous):
            return self._latest_state
        if previous == sequence:
            return self._latest_state

        devices = self._latest_state.setdefault("devices", {})
        if not isinstance(devices, dict):
            return self._latest_state
        device = devices.setdefault(device_name, {})
        if not isinstance(device, dict):
            device = {}
            devices[device_name] = device
        self._merge_dict(device, fields)
        device["sequence"] = sequence
        device["t_ms"] = delta.get("t_ms")
        device.setdefault("status", "ok")
        now_s = time.monotonic()
        self._device_sequences[device_name] = sequence
        self._device_last_received_s[device_name] = now_s
        if device_name == "wristband":
            self._wristband_last_sample_s = now_s
            merged_state = copy.deepcopy(self._latest_state)
            self._wristband_states.append(merged_state)
            return merged_state
        return self._latest_state

    def _store_full_state_locked(self, state: dict[str, Any]) -> dict[str, Any]:
        incoming_devices = state.get("devices")
        current_devices = self._latest_state.get("devices")
        if isinstance(incoming_devices, dict) and isinstance(current_devices, dict):
            for device_name, incoming in list(incoming_devices.items()):
                current = current_devices.get(device_name)
                if not isinstance(incoming, dict) or not isinstance(current, dict):
                    continue
                incoming_sequence = incoming.get("sequence")
                current_sequence = self._device_sequences.get(device_name)
                if isinstance(incoming_sequence, int) and current_sequence is not None:
                    if not self._sequence_is_newer(incoming_sequence, current_sequence):
                        merged = copy.deepcopy(incoming)
                        live_update = {
                            field: current[field]
                            for field in (*DEVICE_LIVE_FIELDS.get(device_name, ()), "status", "sequence", "t_ms")
                            if field in current
                        }
                        self._merge_dict(merged, live_update)
                        incoming_devices[device_name] = merged
        self._latest_state = state
        now_s = time.monotonic()
        if isinstance(incoming_devices, dict):
            for device_name, device in incoming_devices.items():
                if not isinstance(device, dict):
                    continue
                status = str(device.get("status", "")).lower()
                sequence = device.get("sequence")
                if status in DISCONNECTED_STATUSES:
                    self._device_last_received_s.pop(device_name, None)
                    self._device_sequences.pop(device_name, None)
                    continue
                self._device_last_received_s[device_name] = now_s
                if isinstance(sequence, int):
                    self._device_sequences[device_name] = sequence
        return state

    def _store_state_locked(self, state: dict[str, Any]) -> dict[str, Any]:
        device_delta = state.get("device_delta")
        if isinstance(device_delta, dict):
            return self._store_device_delta_locked(device_delta)

        wristband_sample = state.get("wristband_sample")
        if isinstance(wristband_sample, dict):
            return self._store_device_delta_locked(
                {
                    "device": "wristband",
                    "sequence": wristband_sample.get("sequence"),
                    "t_ms": wristband_sample.get("t_ms"),
                    "fields": wristband_sample,
                }
            )

        keyboard_sample = state.get("keyboard_sample")
        if isinstance(keyboard_sample, dict):
            return self._store_device_delta_locked(
                {
                    "device": "keyboard",
                    "sequence": keyboard_sample.get("sequence"),
                    "t_ms": keyboard_sample.get("t_ms"),
                    "fields": keyboard_sample,
                }
            )

        self._store_full_state_locked(state)
        devices = state.get("devices")
        wristband = devices.get("wristband") if isinstance(devices, dict) else None
        status = str(wristband.get("status", "")).lower() if isinstance(wristband, dict) else ""
        if status in DISCONNECTED_STATUSES:
            self._wristband_states.clear()
            self._wristband_last_sample_s = None
        return state

    def send_command(self, command: dict[str, Any], coalesce_key: str | None = None) -> bool:
        line = json.dumps(command, separators=(",", ":")) + "\n"
        with self._serial_lock:
            if not self._serial or not self._serial.is_open:
                return False
        try:
            if coalesce_key:
                should_enqueue = False
                with self._coalesced_lock:
                    self._coalesced_writes[coalesce_key] = line
                    if coalesce_key not in self._queued_coalesce_keys:
                        self._queued_coalesce_keys.add(coalesce_key)
                        should_enqueue = True
                if should_enqueue:
                    self._write_queue.put_nowait(("coalesced", coalesce_key))
            else:
                self._write_queue.put_nowait(("line", line))
            return True
        except queue.Full:
            if coalesce_key:
                with self._coalesced_lock:
                    self._queued_coalesce_keys.discard(coalesce_key)
            self._log("Serial write queue is full; dropping command.")
            return False

    def _write_loop(self) -> None:
        while True:
            try:
                kind, payload = self._write_queue.get()
            except Exception:
                continue
            line: str | None
            if kind == "coalesced":
                if payload is None:
                    continue
                with self._coalesced_lock:
                    line = self._coalesced_writes.pop(payload, None)
                    self._queued_coalesce_keys.discard(payload)
                if line is None:
                    continue
            else:
                line = payload
            if line:
                self._write_line(line)

    def _write_line(self, line: str) -> None:
        with self._serial_lock:
            ser = self._serial
            if not ser or not ser.is_open:
                return
            try:
                ser.write(line.encode("utf-8"))
            except Exception as exc:
                self._log(f"Serial write failed: {exc}")
                self._close_serial()

    def _clear_write_queue(self) -> None:
        with self._coalesced_lock:
            self._coalesced_writes.clear()
            self._queued_coalesce_keys.clear()
        try:
            while True:
                self._write_queue.get_nowait()
        except queue.Empty:
            pass

    def _open_port(self, port: str) -> bool:
        try:
            ser = serial.Serial(
                port=port,
                baudrate=self.baud_rate,
                timeout=0.1,
                write_timeout=0.1,
            )
            with self._serial_lock:
                self._serial = ser
            return True
        except Exception as exc:
            self._log(f"Failed to open {port}: {exc}")
            return False

    def _close_serial(self) -> None:
        with self._serial_lock:
            ser = self._serial
            self._serial = None
        if ser:
            try:
                ser.close()
            except Exception:
                pass

    def _start_reader(self) -> None:
        self._stop_event.clear()
        if self._reader_thread and self._reader_thread.is_alive():
            return
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._serial_lock:
                ser = self._serial

            if ser is None or not ser.is_open:
                if not self._manual_disconnect and self._current_port:
                    time.sleep(0.5)
                    self._open_port(self._current_port)
                else:
                    time.sleep(0.1)
                continue

            try:
                raw = ser.readline()
            except Exception as exc:
                self._log(f"Serial read failed: {exc}")
                self._close_serial()
                continue

            if not raw:
                continue

            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if line.startswith("ANTENNA_"):
                self._log(f"[Antenna] {line}")
                continue

            looks_like_direct_audio_dock = (
                line.startswith("CLAP_SCORES") or
                line.startswith("Triggered!") or
                line.startswith("RECORD_STREAM_") or
                line.startswith("Audio RAM ") or
                line.startswith("AUDIO_DOCK_MAC:")
            )
            if looks_like_direct_audio_dock:
                self._log(
                    "Audio Dock debug output detected on the active serial port. "
                    "Connect the app to the Antenna ESP32-S3 COM port; the Audio Dock should talk wirelessly."
                )
                continue

            is_audiodock = (
                "AUDIODOCK_" in line or 
                "UDIODOCK_" in line or 
                "DOCK_AUDIO" in line or 
                "_AUDIO:" in line
            )

            if is_audiodock:
                first_idx = len(line)
                for p in ["AUDIODOCK_", "UDIODOCK_", "DOCK_AUDIO", "_AUDIO:"]:
                    idx = line.find(p)
                    if 0 <= idx < first_idx:
                        first_idx = idx
                
                if first_idx < len(line) and first_idx > 0:
                    leading = line[:first_idx].strip()
                    if leading:
                        try:
                            state = json.loads(leading)
                            if isinstance(state, dict):
                                with self._latest_lock:
                                    state = self._store_state_locked(state)
                                if self.on_state:
                                    self.on_state(copy.deepcopy(state))
                        except Exception:
                            pass
                
                if self.audio_dock_bridge:
                    self.audio_dock_bridge.handle_antenna_line(line)
                continue

            try:
                state = json.loads(line)
            except json.JSONDecodeError:
                self._log(f"Ignored malformed serial line: {line[:120]}")
                continue

            if not isinstance(state, dict):
                continue

            with self._latest_lock:
                state = self._store_state_locked(state)
            if self.on_state:
                self.on_state(copy.deepcopy(state))
