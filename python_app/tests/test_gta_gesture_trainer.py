from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gta_gesture_trainer import GtaGestureTrainer


class GtaGestureTrainerTests(unittest.TestCase):
    def _write_recording(
        self,
        root: Path,
        gesture_name: str,
        index: int,
        samples: list[dict[str, float | str | None]],
    ) -> None:
        folder = root / gesture_name
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "gesture_name": gesture_name,
            "samples": [
                {"t_rel": sample_index * 0.1, "input_dict": values}
                for sample_index, values in enumerate(samples)
            ],
        }
        (folder / f"sample_{index}.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_trains_personalized_camera_thresholds_and_directions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "gestures"
            for index in range(3):
                self._write_recording(
                    root,
                    "run_forward",
                    index,
                    [{"right_hand_z_mm": value} for value in [700] * 8 + [680, 640, 590, 550, 540]],
                )
                self._write_recording(
                    root,
                    "turn_right",
                    index,
                    [{"left_hand_x": value} for value in [0.55] * 8 + [0.52, 0.48, 0.42, 0.38]],
                )

            model = GtaGestureTrainer(root, Path(tmpdir) / "model.json").train()

        walk = model["rule_thresholds"]["gtavc_right_hand_forward"]["signed_threshold"]
        turn = model["rule_thresholds"]["gtavc_left_palm_turn_right"]["signed_threshold"]
        self.assertGreater(walk, 60)
        self.assertGreater(turn, 0.035)
        self.assertEqual(model["gesture_counts"]["run_forward"], 3)

    def test_trains_wristband_orientation_from_rotation_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "gestures"
            for index in range(3):
                self._write_recording(
                    root,
                    "swap_weapon_next",
                    index,
                    [{"wrist_roll": value} for value in [0] * 8 + [-4, -9, -15, -22, -28]],
                )
                self._write_recording(
                    root,
                    "swap_weapon_previous",
                    index,
                    [{"wrist_roll": value} for value in [0] * 8 + [4, 9, 15, 22, 28]],
                )

            model = GtaGestureTrainer(root, Path(tmpdir) / "model.json").train()

        self.assertEqual(model["wrist"]["clockwise_sign"], -1)
        self.assertEqual(model["wrist"]["counterclockwise_sign"], 1)
        self.assertGreater(model["wrist"]["clockwise_delta_deg"], 4)

    def test_requires_three_valid_samples_before_applying_camera_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "gestures"
            for index in range(2):
                self._write_recording(
                    root,
                    "walk_reverse",
                    index,
                    [{"right_hand_z_mm": value} for value in [700] * 8 + [730, 780, 850]],
                )

            model = GtaGestureTrainer(root, Path(tmpdir) / "model.json").train()

        self.assertNotIn("gtavc_right_hand_backward", model["rule_thresholds"])


if __name__ == "__main__":
    unittest.main()
