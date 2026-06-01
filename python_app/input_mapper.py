from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from config import MAPPING_PATH
from input_backend import InputBackend, normalize_mouse_button, parse_key_combo


MAPPING_SCHEMA_VERSION = 1
DEFAULT_PROFILE_NAME = "Default"
DEFAULT_MAPPING_PATH = MAPPING_PATH

ACTION_TYPES = {
    "keyboard_tap",
    "keyboard_hold",
    "keyboard_repeat",
    "mouse_click",
    "mouse_hold",
    "mouse_scroll",
    "mouse_move",
    "mouse_absolute",
}

COMPARATORS = {
    "lt",
    "lte",
    "gt",
    "gte",
    "between",
    "outside",
    "eq",
    "neq",
    "present",
    "truthy",
    "falsey",
}


@dataclass
class SignalValue:
    id: str
    group: str
    label: str
    value: Any

    @property
    def display_value(self) -> str:
        if self.value is None:
            return "-"
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if isinstance(self.value, float):
            return f"{self.value:.3f}"
        if isinstance(self.value, (dict, list)):
            return json.dumps(self.value, separators=(",", ":"))
        return str(self.value)


class SignalCatalog:
    GROUP_ORDER = {
        "Keyboard": 0,
        "Wristband": 1,
        "Cam Dock": 2,
        "Hands": 3,
        "Camera": 4,
        "Audio Dock": 5,
        "Fans": 6,
        "Fused Input": 7,
        "Antenna": 8,
    }

    @classmethod
    def flatten(cls, snapshot: dict[str, Any]) -> dict[str, SignalValue]:
        signals: dict[str, SignalValue] = {}

        def add(group: str, signal_id: str, label: str, value: Any) -> None:
            signals[signal_id] = SignalValue(signal_id, group, label, value)

        raw_state = snapshot.get("raw_device_state", {}) if isinstance(snapshot, dict) else {}
        input_dict = snapshot.get("input_dict", {}) if isinstance(snapshot, dict) else {}
        hand_state = snapshot.get("hand_state", {}) if isinstance(snapshot, dict) else {}
        face_state = snapshot.get("face_state", {}) if isinstance(snapshot, dict) else {}
        devices = raw_state.get("devices", {}) if isinstance(raw_state, dict) else {}

        add("Antenna", "antenna.connected", "Antenna connected", bool(raw_state))
        if isinstance(raw_state, dict):
            add("Antenna", "antenna.t_ms", "Antenna t_ms", raw_state.get("t_ms"))
            add("Antenna", "antenna.sequence", "Antenna sequence", raw_state.get("sequence"))

        keyboard = devices.get("keyboard", {}) if isinstance(devices, dict) else {}
        keyboard_tof = keyboard.get("tof", {}) if isinstance(keyboard, dict) else {}
        keyboard_valid = keyboard.get("valid", {}) if isinstance(keyboard, dict) else {}
        add("Keyboard", "keyboard.status", "Status", keyboard.get("status") if isinstance(keyboard, dict) else None)
        add("Keyboard", "keyboard.input", "Input state", keyboard.get("input") if isinstance(keyboard, dict) else None)
        add("Keyboard", "keyboard.sequence", "Sequence", keyboard.get("sequence") if isinstance(keyboard, dict) else None)
        for index in range(1, 5):
            add(
                "Keyboard",
                f"keyboard.sensor_{index}_mm",
                f"Sensor {index} distance mm",
                keyboard_tof.get(f"sensor_{index}_mm") if isinstance(keyboard_tof, dict) else None,
            )
            add(
                "Keyboard",
                f"keyboard.sensor_{index}_valid",
                f"Sensor {index} valid",
                keyboard_valid.get(f"sensor_{index}") if isinstance(keyboard_valid, dict) else None,
            )

        wrist = devices.get("wristband", {}) if isinstance(devices, dict) else {}
        wrist_accel = wrist.get("accel", {}) if isinstance(wrist, dict) else {}
        wrist_gyro = wrist.get("gyro", {}) if isinstance(wrist, dict) else {}
        add("Wristband", "wristband.status", "Status", wrist.get("status") if isinstance(wrist, dict) else None)
        add("Wristband", "wristband.sequence", "Sequence", wrist.get("sequence") if isinstance(wrist, dict) else None)
        add("Wristband", "wristband.battery_level", "Battery level", wrist.get("battery_level") if isinstance(wrist, dict) else None)
        add("Wristband", "wristband.pitch", "Pitch", wrist.get("pitch") if isinstance(wrist, dict) else None)
        add("Wristband", "wristband.roll", "Roll", wrist.get("roll") if isinstance(wrist, dict) else None)
        add("Wristband", "wristband.yaw", "Yaw", wrist.get("yaw") if isinstance(wrist, dict) else None)
        for axis in ("x", "y", "z"):
            add("Wristband", f"wristband.accel_{axis}", f"Accel {axis}", wrist_accel.get(axis))
            add("Wristband", f"wristband.gyro_{axis}", f"Gyro {axis}", wrist_gyro.get(axis))

        camdock = devices.get("camdock", {}) if isinstance(devices, dict) else {}
        camdock_tof = camdock.get("tof", {}) if isinstance(camdock, dict) else {}
        add("Cam Dock", "camdock.status", "Status", camdock.get("status") if isinstance(camdock, dict) else None)
        add("Cam Dock", "camdock.sequence", "Sequence", camdock.get("sequence") if isinstance(camdock, dict) else None)
        add("Cam Dock", "camdock.active_target", "Active target", camdock.get("active_target") if isinstance(camdock, dict) else None)
        add("Cam Dock", "camdock.tof_left_mm", "Left ToF mm", camdock_tof.get("left_mm") if isinstance(camdock_tof, dict) else None)
        add("Cam Dock", "camdock.tof_right_mm", "Right ToF mm", camdock_tof.get("right_mm") if isinstance(camdock_tof, dict) else None)
        add("Cam Dock", "camdock.battery_level", "Battery level", camdock.get("battery_level") if isinstance(camdock, dict) else None)

        if isinstance(hand_state, dict):
            for side in ("right", "left"):
                hand = hand_state.get(side, {})
                if not isinstance(hand, dict):
                    hand = {}
                label = side.title()
                add("Hands", f"hands.{side}.visible", f"{label} visible", hand.get("visible"))
                add("Hands", f"hands.{side}.x", f"{label} x", hand.get("x"))
                add("Hands", f"hands.{side}.y", f"{label} image y", hand.get("y"))
                add("Hands", f"hands.{side}.score", f"{label} score", hand.get("score"))
                add("Hands", f"hands.{side}.gesture", f"{label} gesture", hand.get("gesture"))

        if isinstance(face_state, dict):
            add("Camera", "camera.face_visible", "Face visible", face_state.get("visible"))
            add("Camera", "camera.face_x", "Face x", face_state.get("x"))
            add("Camera", "camera.face_top_y", "Face top y", face_state.get("top_y"))
            add("Camera", "camera.face_y", "Face y", face_state.get("y"))

        audiodock = devices.get("audiodock", {}) if isinstance(devices, dict) else {}
        add("Audio Dock", "audiodock.status", "Status", audiodock.get("status") if isinstance(audiodock, dict) else None)
        add("Audio Dock", "audiodock.clap_detected", "Clap detected", audiodock.get("clap_detected") if isinstance(audiodock, dict) else None)
        add("Audio Dock", "audiodock.clap_type", "Clap type", audiodock.get("clap_type") if isinstance(audiodock, dict) else None)

        fans = devices.get("fans", {}) if isinstance(devices, dict) else {}
        fan_temps = fans.get("temps", {}) if isinstance(fans, dict) else {}
        add("Fans", "fans.status", "Status", fans.get("status") if isinstance(fans, dict) else None)
        add("Fans", "fans.input", "Input state", fans.get("input") if isinstance(fans, dict) else None)
        add("Fans", "fans.fan_on", "Fan on", fans.get("fan_on") if isinstance(fans, dict) else None)
        add("Fans", "fans.temp_1_c", "Temp 1 C", fan_temps.get("sensor_1_c") if isinstance(fan_temps, dict) else None)
        add("Fans", "fans.temp_2_c", "Temp 2 C", fan_temps.get("sensor_2_c") if isinstance(fan_temps, dict) else None)

        if isinstance(input_dict, dict):
            for key, value in input_dict.items():
                add("Fused Input", f"fused.{key}", key, value)

        return signals

    @classmethod
    def rows(cls, snapshot: dict[str, Any]) -> list[SignalValue]:
        return sorted(
            cls.flatten(snapshot).values(),
            key=lambda signal: (cls.GROUP_ORDER.get(signal.group, 99), signal.label.lower(), signal.id),
        )


@dataclass
class MappingAction:
    type: str = "keyboard_tap"
    keys: list[str] = field(default_factory=list)
    button: str = "left"
    clicks: int = 1
    interval_ms: int = 250
    scroll_x: int = 0
    scroll_y: int = 1
    speed_x: float = 0.0
    speed_y: float = 0.0
    absolute_x: float = 0.5
    absolute_y: float = 0.5
    continuous: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MappingAction":
        if not isinstance(data, dict):
            raise ValueError("mapping action must be an object")
        action_type = str(data.get("type", "keyboard_tap"))
        if action_type not in ACTION_TYPES:
            raise ValueError(f"unknown mapping action type: {action_type}")
        return cls(
            type=action_type,
            keys=parse_key_combo(data.get("keys", [])),
            button=normalize_mouse_button(str(data.get("button", "left"))),
            clicks=max(1, int(float(data.get("clicks", 1) or 1))),
            interval_ms=max(20, int(float(data.get("interval_ms", 250) or 250))),
            scroll_x=int(float(data.get("scroll_x", 0) or 0)),
            scroll_y=int(float(data.get("scroll_y", 1) or 0)),
            speed_x=float(data.get("speed_x", 0.0) or 0.0),
            speed_y=float(data.get("speed_y", 0.0) or 0.0),
            absolute_x=max(0.0, min(1.0, float(data.get("absolute_x", 0.5) or 0.0))),
            absolute_y=max(0.0, min(1.0, float(data.get("absolute_y", 0.5) or 0.0))),
            continuous=bool(data.get("continuous", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "keys": list(self.keys),
            "button": self.button,
            "clicks": self.clicks,
            "interval_ms": self.interval_ms,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
            "speed_x": self.speed_x,
            "speed_y": self.speed_y,
            "absolute_x": self.absolute_x,
            "absolute_y": self.absolute_y,
            "continuous": self.continuous,
        }

    @property
    def mode(self) -> str:
        if self.type.endswith("_hold"):
            return "hold"
        if self.type in {"keyboard_repeat", "mouse_scroll"}:
            return "repeat"
        if self.type == "mouse_move":
            return "continuous"
        return "tap"

    def summary(self) -> str:
        if self.type.startswith("keyboard"):
            combo = "+".join(self.keys) if self.keys else "(no keys)"
            if self.type == "keyboard_repeat":
                return f"repeat {combo}"
            if self.type == "keyboard_hold":
                return f"hold {combo}"
            return f"tap {combo}"
        if self.type == "mouse_click":
            return f"click {self.button}"
        if self.type == "mouse_hold":
            return f"hold mouse {self.button}"
        if self.type == "mouse_scroll":
            return f"scroll x={self.scroll_x} y={self.scroll_y}"
        if self.type == "mouse_move":
            return f"move x={self.speed_x:g}/s y={self.speed_y:g}/s"
        if self.type == "mouse_absolute":
            return f"move absolute {self.absolute_x:.2f},{self.absolute_y:.2f}"
        return self.type


@dataclass
class MappingRule:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "New mapping"
    enabled: bool = True
    source: str = ""
    comparator: str = "lt"
    threshold: Any = 100.0
    low: Any = 0.0
    high: Any = 1.0
    hysteresis: float = 0.0
    debounce_ms: int = 0
    action: MappingAction = field(default_factory=MappingAction)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MappingRule":
        if not isinstance(data, dict):
            raise ValueError("mapping rule must be an object")
        comparator = str(data.get("comparator", "lt"))
        if comparator not in COMPARATORS:
            raise ValueError(f"unknown comparator: {comparator}")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=str(data.get("name") or "Mapping"),
            enabled=bool(data.get("enabled", True)),
            source=str(data.get("source") or ""),
            comparator=comparator,
            threshold=data.get("threshold", 100.0),
            low=data.get("low", 0.0),
            high=data.get("high", 1.0),
            hysteresis=max(0.0, float(data.get("hysteresis", 0.0) or 0.0)),
            debounce_ms=max(0, int(float(data.get("debounce_ms", 0) or 0))),
            action=MappingAction.from_dict(data.get("action", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "source": self.source,
            "comparator": self.comparator,
            "threshold": self.threshold,
            "low": self.low,
            "high": self.high,
            "hysteresis": self.hysteresis,
            "debounce_ms": self.debounce_ms,
            "action": self.action.to_dict(),
        }

    def condition_summary(self) -> str:
        if self.comparator in {"present", "truthy", "falsey"}:
            return self.comparator
        if self.comparator in {"between", "outside"}:
            return f"{self.comparator} {self.low}..{self.high}"
        return f"{self.comparator} {self.threshold}"


@dataclass
class MappingProfile:
    name: str = DEFAULT_PROFILE_NAME
    mappings: list[MappingRule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MappingProfile":
        if not isinstance(data, dict):
            raise ValueError("profile must be an object")
        mappings = [MappingRule.from_dict(item) for item in data.get("mappings", [])]
        return cls(name=str(data.get("name") or DEFAULT_PROFILE_NAME), mappings=mappings)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "mappings": [rule.to_dict() for rule in self.mappings]}


@dataclass
class MappingConfig:
    version: int = MAPPING_SCHEMA_VERSION
    enabled_on_start: bool = False
    active_profile: str = DEFAULT_PROFILE_NAME
    profiles: list[MappingProfile] = field(default_factory=lambda: [MappingProfile()])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MappingConfig":
        if not isinstance(data, dict):
            raise ValueError("mapping config must be an object")
        version = int(data.get("version", 0))
        if version != MAPPING_SCHEMA_VERSION:
            raise ValueError(f"unsupported mapping config version: {version}")
        profiles = [MappingProfile.from_dict(item) for item in data.get("profiles", [])]
        if not profiles:
            profiles = [MappingProfile()]
        active_profile = str(data.get("active_profile") or profiles[0].name)
        if active_profile not in {profile.name for profile in profiles}:
            active_profile = profiles[0].name
        return cls(
            version=version,
            enabled_on_start=bool(data.get("enabled_on_start", False)),
            active_profile=active_profile,
            profiles=profiles,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "enabled_on_start": self.enabled_on_start,
            "active_profile": self.active_profile,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }

    def active(self) -> MappingProfile:
        for profile in self.profiles:
            if profile.name == self.active_profile:
                return profile
        self.active_profile = self.profiles[0].name
        return self.profiles[0]

    def profile_names(self) -> list[str]:
        return [profile.name for profile in self.profiles]


def default_mapping_config() -> MappingConfig:
    return MappingConfig()


def load_mapping_config(path: Path = DEFAULT_MAPPING_PATH) -> tuple[MappingConfig, str | None]:
    if not path.exists():
        return default_mapping_config(), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return MappingConfig.from_dict(data), None
    except Exception as exc:
        return default_mapping_config(), str(exc)


def save_mapping_config(config: MappingConfig, path: Path = DEFAULT_MAPPING_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")


@dataclass
class _RuntimeState:
    active: bool = False
    pending_desired: bool | None = None
    pending_since_s: float = 0.0
    last_fired_s: float | None = None
    last_repeat_s: float = 0.0
    last_process_s: float | None = None
    residual_x: float = 0.0
    residual_y: float = 0.0
    status: str = "idle"


class InputMapper:
    def __init__(
        self,
        backend: InputBackend,
        config: MappingConfig | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self.backend = backend
        self.config = config or default_mapping_config()
        self.on_log = on_log
        self.enabled = bool(self.config.enabled_on_start)
        self._states: dict[str, _RuntimeState] = {}
        self._held_keys: dict[str, set[str]] = {}
        self._held_buttons: dict[str, set[str]] = {}
        self._rule_keys: dict[str, set[str]] = {}
        self._rule_buttons: dict[str, set[str]] = {}
        self._last_status = "armed" if self.enabled else "disabled"

    @property
    def last_status(self) -> str:
        if not self.backend.available:
            return self.backend.error or "input backend unavailable"
        return self._last_status

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self.enabled == enabled:
            return
        self.enabled = enabled
        self._last_status = "armed" if enabled else "disabled"
        if not enabled:
            self.release_all()

    def set_config(self, config: MappingConfig) -> None:
        self.release_all()
        self.config = config
        self.enabled = bool(config.enabled_on_start)
        self._states.clear()

    def set_active_profile(self, profile_name: str) -> bool:
        if profile_name not in self.config.profile_names():
            return False
        if self.config.active_profile != profile_name:
            self.release_all()
            self.config.active_profile = profile_name
            self._states.clear()
        return True

    def active_rules(self) -> list[MappingRule]:
        return self.config.active().mappings

    def process(self, snapshot: dict[str, Any], now_s: float | None = None, suppress_output: bool = False) -> None:
        now_s = time.monotonic() if now_s is None else now_s
        if suppress_output:
            if self.has_held_outputs:
                self.release_all()
            self._last_status = "suppressed"
            return
        if not self.enabled:
            if self.has_held_outputs:
                self.release_all()
            self._last_status = "disabled"
            return
        if not self.backend.available:
            if self.has_held_outputs:
                self.release_all()
            self._last_status = self.backend.error or "input backend unavailable"
            return

        signals = SignalCatalog.flatten(snapshot)
        live_rule_ids = set()
        for rule in self.active_rules():
            live_rule_ids.add(rule.id)
            state = self._states.setdefault(rule.id, _RuntimeState())
            if not rule.enabled or not rule.source:
                self._transition(rule, state, False, now_s)
                state.status = "disabled" if not rule.enabled else "no source"
                continue
            signal = signals.get(rule.source)
            if signal is None or signal.value is None:
                state.pending_desired = None
                self._transition(rule, state, False, now_s)
                state.status = "missing"
                continue

            desired = evaluate_condition(rule, signal.value, state.active)
            active = self._debounced_active(rule, state, desired, now_s)
            self._transition(rule, state, active, now_s, signal.value)
            state.status = "active" if state.active else "idle"

        for rule_id, state in list(self._states.items()):
            if rule_id not in live_rule_ids and state.active:
                self.release_rule(rule_id)
                state.active = False
                state.status = "removed"
        self._last_status = "armed"

    @property
    def has_held_outputs(self) -> bool:
        return bool(self._held_keys or self._held_buttons)

    def release_rule(self, rule_id: str) -> None:
        for token in list(self._rule_keys.get(rule_id, set())):
            holders = self._held_keys.get(token)
            if not holders:
                continue
            holders.discard(rule_id)
            if not holders:
                self.backend.release_key(token)
                self._held_keys.pop(token, None)
        for button in list(self._rule_buttons.get(rule_id, set())):
            holders = self._held_buttons.get(button)
            if not holders:
                continue
            holders.discard(rule_id)
            if not holders:
                self.backend.release_mouse(button)
                self._held_buttons.pop(button, None)
        self._rule_keys.pop(rule_id, None)
        self._rule_buttons.pop(rule_id, None)

    def release_all(self) -> None:
        for token in list(self._held_keys.keys()):
            self.backend.release_key(token)
        for button in list(self._held_buttons.keys()):
            self.backend.release_mouse(button)
        self._held_keys.clear()
        self._held_buttons.clear()
        self._rule_keys.clear()
        self._rule_buttons.clear()
        for state in self._states.values():
            state.active = False
            state.pending_desired = None
            state.status = "idle"

    def test_action(self, action: MappingAction) -> None:
        if not self.backend.available:
            self._log(self.backend.error or "Input backend unavailable.")
            return
        if action.type == "keyboard_hold":
            self.backend.tap_keys(action.keys)
            return
        if action.type == "mouse_hold":
            self.backend.click_mouse(action.button, 1)
            return
        self._execute_enter("__test__", action, time.monotonic())

    def state_for_rule(self, rule_id: str) -> _RuntimeState:
        return self._states.setdefault(rule_id, _RuntimeState())

    def _debounced_active(self, rule: MappingRule, state: _RuntimeState, desired: bool, now_s: float) -> bool:
        if desired == state.active:
            state.pending_desired = None
            return state.active
        debounce_s = rule.debounce_ms / 1000.0
        if debounce_s <= 0:
            state.pending_desired = None
            return desired
        if state.pending_desired != desired:
            state.pending_desired = desired
            state.pending_since_s = now_s
            return state.active
        if now_s - state.pending_since_s >= debounce_s:
            state.pending_desired = None
            return desired
        return state.active

    def _transition(
        self,
        rule: MappingRule,
        state: _RuntimeState,
        active: bool,
        now_s: float,
        source_value: Any = None,
    ) -> None:
        if active and not state.active:
            state.active = True
            state.last_process_s = now_s
            state.residual_x = 0.0
            state.residual_y = 0.0
            self._execute_enter(rule.id, rule.action, now_s)
        elif not active and state.active:
            state.active = False
            state.last_process_s = None
            self.release_rule(rule.id)
            return

        if state.active:
            self._execute_active(rule.id, rule.action, state, now_s, source_value)

    def _execute_enter(self, rule_id: str, action: MappingAction, now_s: float) -> None:
        if action.type == "keyboard_tap":
            self.backend.tap_keys(action.keys)
        elif action.type == "keyboard_hold":
            self._hold_keys(rule_id, action.keys)
        elif action.type == "keyboard_repeat":
            self.backend.tap_keys(action.keys)
        elif action.type == "mouse_click":
            self.backend.click_mouse(action.button, action.clicks)
        elif action.type == "mouse_hold":
            self._hold_mouse(rule_id, action.button)
        elif action.type == "mouse_scroll":
            self.backend.scroll(action.scroll_x, action.scroll_y)
        elif action.type == "mouse_absolute":
            self._move_absolute(action)
        state = self._states.setdefault(rule_id, _RuntimeState())
        state.last_fired_s = now_s
        state.last_repeat_s = now_s

    def _execute_active(
        self,
        rule_id: str,
        action: MappingAction,
        state: _RuntimeState,
        now_s: float,
        source_value: Any,
    ) -> None:
        interval_s = max(0.02, action.interval_ms / 1000.0)
        if action.type == "keyboard_repeat" and now_s - state.last_repeat_s >= interval_s:
            self.backend.tap_keys(action.keys)
            state.last_fired_s = now_s
            state.last_repeat_s = now_s
        elif action.type == "mouse_scroll" and now_s - state.last_repeat_s >= interval_s:
            self.backend.scroll(action.scroll_x, action.scroll_y)
            state.last_fired_s = now_s
            state.last_repeat_s = now_s
        elif action.type == "mouse_move":
            last = state.last_process_s if state.last_process_s is not None else now_s
            dt = max(0.0, min(0.2, now_s - last))
            state.last_process_s = now_s
            self._move_relative(action, state, dt, now_s)
        elif action.type == "mouse_absolute" and action.continuous:
            self._move_absolute(action)
            state.last_fired_s = now_s

    def _hold_keys(self, rule_id: str, tokens: list[str]) -> None:
        for token in tokens:
            if not token:
                continue
            holders = self._held_keys.setdefault(token, set())
            if not holders:
                self.backend.press_key(token)
            holders.add(rule_id)
            self._rule_keys.setdefault(rule_id, set()).add(token)

    def _hold_mouse(self, rule_id: str, button: str) -> None:
        button = normalize_mouse_button(button)
        holders = self._held_buttons.setdefault(button, set())
        if not holders:
            self.backend.press_mouse(button)
        holders.add(rule_id)
        self._rule_buttons.setdefault(rule_id, set()).add(button)

    def _move_relative(self, action: MappingAction, state: _RuntimeState, dt: float, now_s: float) -> None:
        move_x = (action.speed_x * dt) + state.residual_x
        move_y = (action.speed_y * dt) + state.residual_y
        step_x = int(move_x)
        step_y = int(move_y)
        state.residual_x = move_x - step_x
        state.residual_y = move_y - step_y
        if step_x or step_y:
            self.backend.move(step_x, step_y)
            state.last_fired_s = now_s

    def _move_absolute(self, action: MappingAction) -> None:
        try:
            import tkinter as tk

            root = tk._default_root
            width = root.winfo_screenwidth() if root is not None else 1920
            height = root.winfo_screenheight() if root is not None else 1080
        except Exception:
            width, height = 1920, 1080
        x = int(max(0.0, min(1.0, action.absolute_x)) * max(1, width - 1))
        y = int(max(0.0, min(1.0, action.absolute_y)) * max(1, height - 1))
        self.backend.move_absolute(x, y)

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)


def evaluate_condition(rule: MappingRule, value: Any, was_active: bool = False) -> bool:
    comparator = rule.comparator
    hysteresis = max(0.0, float(rule.hysteresis or 0.0))
    if comparator == "present":
        return value is not None and value != ""
    if comparator == "truthy":
        return bool(value)
    if comparator == "falsey":
        return not bool(value)
    if comparator in {"eq", "neq"}:
        same = _compare_equal(value, rule.threshold)
        return same if comparator == "eq" else not same

    number = _to_number(value)
    if number is None:
        return False
    threshold = _to_number(rule.threshold)
    low = _to_number(rule.low)
    high = _to_number(rule.high)
    if comparator in {"lt", "lte", "gt", "gte"} and threshold is None:
        return False
    if comparator in {"between", "outside"} and (low is None or high is None):
        return False

    if comparator == "lt":
        return number <= threshold + hysteresis if was_active else number < threshold
    if comparator == "lte":
        return number <= threshold + hysteresis if was_active else number <= threshold
    if comparator == "gt":
        return number >= threshold - hysteresis if was_active else number > threshold
    if comparator == "gte":
        return number >= threshold - hysteresis if was_active else number >= threshold
    if comparator == "between":
        lo, hi = sorted((low, high))
        if was_active:
            return lo - hysteresis <= number <= hi + hysteresis
        return lo <= number <= hi
    if comparator == "outside":
        lo, hi = sorted((low, high))
        if was_active:
            return number < lo + hysteresis or number > hi - hysteresis
        return number < lo or number > hi
    return False


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compare_equal(left: Any, right: Any) -> bool:
    left_number = _to_number(left)
    right_number = _to_number(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    return str(left).strip().lower() == str(right).strip().lower()
