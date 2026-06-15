from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fusion_state import FIELD_ORDER, FusionState


REMOVED_FIELDS = {
    "keyboard_input",
    "wrist_pitch_delta",
    "wrist_roll_delta",
    "wrist_pitch_abs_delta",
    "wrist_roll_abs_delta",
    "wrist_pitch_dominant",
    "wrist_roll_dominant",
    "wrist_dominant_axis",
    "wrist_motion_roll_delta",
    "wrist_motion_pitch_delta",
    "wrist_motion_roll_abs_delta",
    "wrist_motion_pitch_abs_delta",
    "wrist_motion",
    "wrist_roll_right_detected",
    "wrist_roll_left_detected",
    "wrist_roll_right_then_neutral_detected",
    "wrist_roll_velocity_dps",
    "wrist_pitch_velocity_dps",
    "wrist_roll_velocity_abs_dps",
    "wrist_pitch_velocity_abs_dps",
    "wrist_roll_velocity_peak_dps",
    "wrist_pitch_velocity_peak_dps",
    "wrist_roll_velocity_peak_ratio",
    "wrist_pitch_velocity_peak_ratio",
    "wrist_roll_velocity_peak_detected",
    "wrist_pitch_velocity_peak_detected",
    "wrist_roll_velocity_profile",
    "wrist_pitch_velocity_profile",
    "wrist_roll_candidate_active",
    "wrist_pitch_candidate_active",
    "wrist_pitch_up_detected",
    "wrist_pitch_down_detected",
    "wrist_roll_event_cooldown_active",
    "wrist_roll_event_blocked",
    "wrist_roll_event_pulse_active",
}


def serial_state() -> dict[str, object]:
    return {
        "devices": {
            "wristband": {
                "pitch": 12.5,
                "roll": -34.0,
                "battery_level": 87,
                "accel": {"x": 1.1, "y": 2.2, "z": 3.3},
                "gyro": {"x": 4.4, "y": 5.5, "z": 6.6},
            },
            "camdock": {"battery_level": 91, "tof": {"left_mm": 320, "right_mm": 420}},
            "keyboard": {
                "tof": {
                    "sensor_1_mm": 101,
                    "sensor_2_mm": 102,
                    "sensor_3_mm": 103,
                    "sensor_4_mm": 104,
                }
            },
            "charging_dock": {"input": "charging"},
            "audiodock": {"input": "open menu"},
            "fans": {"battery_level": 73, "input": "on"},
        }
    }


def hands() -> dict[str, dict[str, object]]:
    return {
        "right": {"visible": True, "x": 0.25, "y": 0.2, "gesture": "open_palm"},
        "left": {"visible": True, "x": 0.75, "y": 0.8, "gesture": "closed_fist"},
    }


class FusionStateTests(unittest.TestCase):
    def test_field_order_is_reduced_for_mapping(self) -> None:
        self.assertEqual(len(FIELD_ORDER), 26)
        self.assertIn("base_z", FIELD_ORDER)
        self.assertIn("wrist_rule_value", FIELD_ORDER)
        for field in (
            "model_value",
            "wrist_pitch",
            "wrist_roll",
            "wrist_rotate_left_return",
            "wrist_rotate_right_return",
        ):
            self.assertNotIn(field, FIELD_ORDER)
        for field in REMOVED_FIELDS:
            self.assertNotIn(field, FIELD_ORDER)

    def test_build_input_dict_keeps_raw_imu_and_model_value(self) -> None:
        values = FusionState().build_input_dict(serial_state(), hands(), model_value="rotate_right")

        self.assertEqual(values["wrist_accel_x"], 1.1)
        self.assertEqual(values["wrist_accel_y"], 2.2)
        self.assertEqual(values["wrist_accel_z"], 3.3)
        self.assertEqual(values["wrist_gyro_x"], 4.4)
        self.assertEqual(values["wrist_gyro_y"], 5.5)
        self.assertEqual(values["wrist_gyro_z"], 6.6)
        self.assertEqual(values["wrist_pitch"], 12.5)
        self.assertEqual(values["wrist_roll"], -34.0)
        self.assertEqual(values["model_value"], "rotate_right")

    def test_model_value_defaults_to_none_string(self) -> None:
        values = FusionState().build_input_dict(serial_state(), hands())

        self.assertEqual(values["model_value"], "none")
        self.assertEqual(values["wrist_rule_value"], "none")
        self.assertFalse(values["wrist_rotate_left_return"])
        self.assertFalse(values["wrist_rotate_right_return"])

    def test_rule_detector_outputs_are_mapper_ready(self) -> None:
        values = FusionState().build_input_dict(
            serial_state(),
            hands(),
            wrist_rule_value="rotate_left_return",
            wrist_rotate_left_return=True,
        )

        self.assertEqual(values["wrist_rule_value"], "rotate_left_return")
        self.assertTrue(values["wrist_rotate_left_return"])

    def test_input_array_matches_field_order(self) -> None:
        fusion = FusionState()
        values = fusion.build_input_dict(serial_state(), hands(), model_value="flick")
        array = fusion.build_input_array(values)

        self.assertEqual(len(array), len(FIELD_ORDER))
        self.assertEqual(array[FIELD_ORDER.index("wrist_rule_value")], "none")

    def test_hand_y_is_converted_to_up_coordinate(self) -> None:
        values = FusionState().build_input_dict(serial_state(), hands(), model_value="none")

        self.assertAlmostEqual(values["right_hand_y"], 0.8)
        self.assertAlmostEqual(values["left_hand_y"], 0.2)

    def test_base_z_is_exposed_for_mapping(self) -> None:
        values = FusionState().build_input_dict(serial_state(), hands(), base_z=515.5)

        self.assertEqual(values["base_z"], 515.5)


if __name__ == "__main__":
    unittest.main()
