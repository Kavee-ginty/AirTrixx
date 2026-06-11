from __future__ import annotations

from typing import Any


GESTURE_SUSTAINED_MIN_MS = 120


FIELD_ORDER = [
    "right_hand_x",
    "right_hand_y",
    "right_hand_z_mm",
    "right_hand_gesture",
    "left_hand_x",
    "left_hand_y",
    "left_hand_z_mm",
    "left_hand_gesture",
    "wrist_accel_x",
    "wrist_accel_y",
    "wrist_accel_z",
    "wrist_gyro_x",
    "wrist_gyro_y",
    "wrist_gyro_z",
    "wrist_pitch",
    "wrist_roll",
    "camdock_battery_level",
    "wristband_battery_level",
    "fans_battery_level",
    "keyboard_sensor_1_mm",
    "keyboard_sensor_2_mm",
    "keyboard_sensor_3_mm",
    "keyboard_sensor_4_mm",
    "charging_dock_input",
    "audiodock_input",
    "fans_input",
    "model_value",
    "wrist_rule_value",
    "wrist_rotate_left_return",
    "wrist_rotate_right_return",
]


class FusionState:
    @staticmethod
    def _camera_y_up(values: dict[str, Any]) -> float | None:
        if not values.get("visible") or values.get("y") is None:
            return None
        try:
            image_y = float(values["y"])
        except (TypeError, ValueError):
            return None
        image_y = max(0.0, min(1.0, image_y))
        return 1.0 - image_y

    def build_input_dict(
        self,
        serial_state: dict[str, Any],
        hand_state: dict[str, dict[str, Any]],
        now_s: float | None = None,
        model_value: str | None = None,
        wrist_rule_value: str | None = None,
        wrist_rotate_left_return: bool = False,
        wrist_rotate_right_return: bool = False,
    ) -> dict[str, Any]:
        devices = serial_state.get("devices", {}) if isinstance(serial_state, dict) else {}
        wrist = devices.get("wristband", {}) if isinstance(devices, dict) else {}
        camdock = devices.get("camdock", {}) if isinstance(devices, dict) else {}
        keyboard = devices.get("keyboard", {}) if isinstance(devices, dict) else {}
        charging_dock = devices.get("charging_dock", {}) if isinstance(devices, dict) else {}
        audiodock = devices.get("audiodock", {}) if isinstance(devices, dict) else {}
        fans = devices.get("fans", {}) if isinstance(devices, dict) else {}
        tof = camdock.get("tof", {}) if isinstance(camdock, dict) else {}
        keyboard_tof = keyboard.get("tof", {}) if isinstance(keyboard, dict) else {}
        accel = wrist.get("accel", {}) if isinstance(wrist, dict) else {}
        gyro = wrist.get("gyro", {}) if isinstance(wrist, dict) else {}
        right = hand_state.get("right", {}) if isinstance(hand_state, dict) else {}
        left = hand_state.get("left", {}) if isinstance(hand_state, dict) else {}
        audiodock_input = audiodock.get("input") if isinstance(audiodock, dict) else None

        return {
            "right_hand_x": right.get("x") if right.get("visible") else None,
            "right_hand_y": self._camera_y_up(right),
            "right_hand_z_mm": tof.get("right_mm"),
            "right_hand_gesture": right.get("gesture") if right.get("visible") else None,
            "left_hand_x": left.get("x") if left.get("visible") else None,
            "left_hand_y": self._camera_y_up(left),
            "left_hand_z_mm": tof.get("left_mm"),
            "left_hand_gesture": left.get("gesture") if left.get("visible") else None,
            "wrist_accel_x": accel.get("x"),
            "wrist_accel_y": accel.get("y"),
            "wrist_accel_z": accel.get("z"),
            "wrist_gyro_x": gyro.get("x"),
            "wrist_gyro_y": gyro.get("y"),
            "wrist_gyro_z": gyro.get("z"),
            "wrist_pitch": wrist.get("pitch") if isinstance(wrist, dict) else None,
            "wrist_roll": wrist.get("roll") if isinstance(wrist, dict) else None,
            "camdock_battery_level": camdock.get("battery_level") if isinstance(camdock, dict) else None,
            "wristband_battery_level": wrist.get("battery_level") if isinstance(wrist, dict) else None,
            "fans_battery_level": fans.get("battery_level") if isinstance(fans, dict) else None,
            "keyboard_sensor_1_mm": keyboard_tof.get("sensor_1_mm") if isinstance(keyboard_tof, dict) else None,
            "keyboard_sensor_2_mm": keyboard_tof.get("sensor_2_mm") if isinstance(keyboard_tof, dict) else None,
            "keyboard_sensor_3_mm": keyboard_tof.get("sensor_3_mm") if isinstance(keyboard_tof, dict) else None,
            "keyboard_sensor_4_mm": keyboard_tof.get("sensor_4_mm") if isinstance(keyboard_tof, dict) else None,
            "charging_dock_input": charging_dock.get("input") if isinstance(charging_dock, dict) else None,
            "audiodock_input": audiodock_input if audiodock_input not in (None, "") else "TBD",
            "fans_input": fans.get("input") if isinstance(fans, dict) else None,
            "model_value": str(model_value or "none"),
            "wrist_rule_value": str(wrist_rule_value or "none"),
            "wrist_rotate_left_return": bool(wrist_rotate_left_return),
            "wrist_rotate_right_return": bool(wrist_rotate_right_return),
        }

    def build_input_array(self, input_dict: dict[str, Any]) -> list[Any]:
        return [input_dict.get(field) for field in FIELD_ORDER]

    def build_snapshot(
        self,
        serial_state: dict[str, Any],
        hand_state: dict[str, dict[str, Any]],
        now_s: float | None = None,
        model_value: str | None = None,
        wrist_rule_value: str | None = None,
        wrist_rotate_left_return: bool = False,
        wrist_rotate_right_return: bool = False,
    ) -> dict[str, Any]:
        input_dict = self.build_input_dict(
            serial_state,
            hand_state,
            now_s=now_s,
            model_value=model_value,
            wrist_rule_value=wrist_rule_value,
            wrist_rotate_left_return=wrist_rotate_left_return,
            wrist_rotate_right_return=wrist_rotate_right_return,
        )
        return {
            "field_order": FIELD_ORDER,
            "input_dict": input_dict,
            "input_array": self.build_input_array(input_dict),
            "raw_device_state": serial_state,
            "hand_state": hand_state,
        }
