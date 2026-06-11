from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class WristRuleConfig:
    enabled: bool = True
    first_peak_dps: float = 180.0
    second_peak_dps: float = 160.0
    neutral_dps: float = 35.0
    max_other_axis_dps: float = 110.0
    dominance_ratio: float = 1.8
    opposite_timeout_s: float = 0.9
    min_duration_s: float = 0.3
    max_duration_s: float = 1.4
    neutral_hold_s: float = 0.15
    cooldown_s: float = 0.7
    min_total_rotation_deg: float = 90.0
    max_signed_rotation_deg: float = 80.0
    pulse_s: float = 0.25
    bias_quiet_dps: float = 30.0
    bias_alpha: float = 0.02


class WristReturnRuleDetector:
    def __init__(self, config: WristRuleConfig | None = None) -> None:
        self.config = config or WristRuleConfig()
        self._gyro_history = [deque(maxlen=3), deque(maxlen=3), deque(maxlen=3)]
        self.bias = [0.0, 0.0, 0.0]
        self.corrected_gyro = [0.0, 0.0, 0.0]
        self.reset()

    def reset(self) -> None:
        for history in self._gyro_history:
            history.clear()
        self.corrected_gyro = [0.0, 0.0, 0.0]
        self.state = "idle"
        self.direction = ""
        self.last_packet_s: float | None = None
        self.event_start_s = 0.0
        self.neutral_since_s: float | None = None
        self.cooldown_until_s = 0.0
        self.signed_rotation_deg = 0.0
        self.total_rotation_deg = 0.0
        self.first_peak_dps = 0.0
        self.second_peak_dps = 0.0
        self.last_event = "none"
        self.last_event_time_s: float | None = None
        self.pulse_until_s = 0.0
        self.rejection_reason = ""

    def process_serial_state(self, serial_state: dict[str, Any], *, now_s: float) -> str | None:
        devices = serial_state.get("devices", {}) if isinstance(serial_state, dict) else {}
        wrist = devices.get("wristband", {}) if isinstance(devices, dict) else {}
        if not isinstance(wrist, dict):
            return None
        if str(wrist.get("status", "")).lower() in {"not_connected", "disconnected", "tbd"}:
            self.reset()
            return None
        gyro = wrist.get("gyro", {})
        packet_ms = wrist.get("t_ms")
        if not isinstance(gyro, dict) or not isinstance(packet_ms, (int, float)):
            return None
        try:
            return self.process(
                float(packet_ms) / 1000.0,
                float(gyro["x"]),
                float(gyro["y"]),
                float(gyro["z"]),
                now_s=now_s,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def process(self, packet_s: float, gyro_x: float, gyro_y: float, gyro_z: float, *, now_s: float) -> str | None:
        if not self.config.enabled:
            self.reset()
            return None
        if self.last_packet_s is not None and packet_s < self.last_packet_s:
            self.reset()

        filtered = self._median_filter(gyro_x, gyro_y, gyro_z)
        if self.state == "idle" and max(abs(value) for value in filtered) <= self.config.bias_quiet_dps:
            for index, value in enumerate(filtered):
                self.bias[index] += self.config.bias_alpha * (value - self.bias[index])
        corrected = [filtered[index] - self.bias[index] for index in range(3)]
        self.corrected_gyro = corrected

        dt_s = 0.0 if self.last_packet_s is None else max(0.0, min(0.1, packet_s - self.last_packet_s))
        self.last_packet_s = packet_s
        gx, gy, gz = corrected

        if self.state == "cooldown":
            if packet_s >= self.cooldown_until_s:
                self.state = "idle"
                self.direction = ""
                self.rejection_reason = ""
            return None

        if self.state == "idle":
            if self._valid_peak(gy, gx, gz, self.config.first_peak_dps):
                self.direction = "right" if gy > 0 else "left"
                self.state = "wait_opposite"
                self.event_start_s = packet_s
                self.neutral_since_s = None
                self.signed_rotation_deg = 0.0
                self.total_rotation_deg = 0.0
                self.first_peak_dps = gy
                self.second_peak_dps = 0.0
                self.rejection_reason = ""
            return None

        self.signed_rotation_deg += gy * dt_s
        self.total_rotation_deg += abs(gy) * dt_s
        elapsed_s = packet_s - self.event_start_s
        if abs(gx) > self.config.max_other_axis_dps or abs(gz) > self.config.max_other_axis_dps:
            self._reject(packet_s, "other axis too large")
            return None

        if self.state == "wait_opposite":
            if elapsed_s > self.config.opposite_timeout_s:
                self._reject(packet_s, "opposite peak timeout")
                return None
            expected_opposite = (
                self.direction == "right" and gy <= -self.config.second_peak_dps
            ) or (
                self.direction == "left" and gy >= self.config.second_peak_dps
            )
            if expected_opposite and self._valid_peak(gy, gx, gz, self.config.second_peak_dps):
                self.second_peak_dps = gy
                self.state = "wait_neutral"
            return None

        if elapsed_s > self.config.max_duration_s:
            self._reject(packet_s, "gesture duration exceeded")
            return None
        if abs(gy) <= self.config.neutral_dps:
            if self.neutral_since_s is None:
                self.neutral_since_s = packet_s
            elif packet_s - self.neutral_since_s >= self.config.neutral_hold_s:
                if elapsed_s < self.config.min_duration_s:
                    self._reject(packet_s, "gesture too short")
                    return None
                if self.total_rotation_deg < self.config.min_total_rotation_deg:
                    self._reject(packet_s, "rotation too small")
                    return None
                if abs(self.signed_rotation_deg) > self.config.max_signed_rotation_deg:
                    self._reject(packet_s, "did not return")
                    return None
                event = f"rotate_{self.direction}_return"
                self.last_event = event
                self.last_event_time_s = now_s
                self.pulse_until_s = now_s + self.config.pulse_s
                self.state = "cooldown"
                self.cooldown_until_s = packet_s + self.config.cooldown_s
                self.rejection_reason = ""
                return event
        else:
            self.neutral_since_s = None
        return None

    def output(self, now_s: float) -> dict[str, Any]:
        value = self.last_event if now_s <= self.pulse_until_s else "none"
        return {
            "value": value,
            "rotate_left_return": value == "rotate_left_return",
            "rotate_right_return": value == "rotate_right_return",
            "state": self.state,
            "direction": self.direction or "none",
            "gyro_x": self.corrected_gyro[0],
            "gyro_y": self.corrected_gyro[1],
            "gyro_z": self.corrected_gyro[2],
            "signed_rotation_deg": self.signed_rotation_deg,
            "total_rotation_deg": self.total_rotation_deg,
            "first_peak_dps": self.first_peak_dps,
            "second_peak_dps": self.second_peak_dps,
            "last_event": self.last_event,
            "rejection_reason": self.rejection_reason,
        }

    def _median_filter(self, gyro_x: float, gyro_y: float, gyro_z: float) -> list[float]:
        values = (gyro_x, gyro_y, gyro_z)
        for history, value in zip(self._gyro_history, values):
            history.append(float(value))
        return [float(statistics.median(history)) for history in self._gyro_history]

    def _valid_peak(self, gyro_y: float, gyro_x: float, gyro_z: float, threshold: float) -> bool:
        other = max(abs(gyro_x), abs(gyro_z), 1.0)
        return (
            abs(gyro_y) >= threshold
            and abs(gyro_x) <= self.config.max_other_axis_dps
            and abs(gyro_z) <= self.config.max_other_axis_dps
            and abs(gyro_y) >= self.config.dominance_ratio * other
        )

    def _reject(self, packet_s: float, reason: str) -> None:
        self.state = "cooldown"
        self.cooldown_until_s = packet_s + self.config.cooldown_s
        self.rejection_reason = reason
