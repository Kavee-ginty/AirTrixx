from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from input_backend import FakeInputBackend
from input_mapper import (
    GESTURE_COOLDOWN_SEC,
    InputMapper,
    MappingAction,
    MappingCondition,
    MappingConfig,
    MappingRule,
    THREEDVIEWER_PROFILE_NAME,
    WINDOWS_3D_VIEWER_PROFILE_NAME,
    SignalCatalog,
    default_mapping_config,
    evaluate_condition,
    load_mapping_config,
    save_mapping_config,
)


def snapshot(**values):
    return {"input_dict": values}


def hand_snapshot(
    values: dict[str, object],
    *,
    left_gesture: str | None = None,
    right_visible: bool = False,
) -> dict[str, object]:
    return {
        "input_dict": values,
        "hand_state": {
            "left": {
                "visible": left_gesture is not None,
                "x": 0.5,
                "y": 0.5,
                "score": 1.0 if left_gesture is not None else 0.0,
                "gesture": left_gesture or "none",
            },
            "right": {
                "visible": right_visible,
                "x": 0.5 if right_visible else None,
                "y": 0.5 if right_visible else None,
                "score": 1.0 if right_visible else 0.0,
                "gesture": "open_palm" if right_visible else "none",
            },
        },
    }


class InputMapperConditionTests(unittest.TestCase):
    def test_numeric_hysteresis_for_less_than(self) -> None:
        rule = MappingRule(comparator="lt", threshold=100, hysteresis=10)
        self.assertTrue(evaluate_condition(rule, 90, False))
        self.assertTrue(evaluate_condition(rule, 105, True))
        self.assertFalse(evaluate_condition(rule, 111, True))

    def test_between_and_equals(self) -> None:
        between = MappingRule(comparator="between", low=10, high=20)
        equals = MappingRule(comparator="eq", threshold="ok")
        self.assertTrue(evaluate_condition(between, 15))
        self.assertFalse(evaluate_condition(between, 25))
        self.assertTrue(evaluate_condition(equals, "OK"))


class InputMapperRuntimeTests(unittest.TestCase):
    def mapper_with(self, rules: list[MappingRule]) -> tuple[InputMapper, FakeInputBackend]:
        backend = FakeInputBackend()
        mapper = InputMapper(backend)
        mapper.set_enabled(True)
        mapper.config.active().mappings = rules
        return mapper, backend

    def test_tap_fires_on_activation_only(self) -> None:
        rule = MappingRule(
            source="fused.a",
            comparator="gt",
            threshold=0,
            action=MappingAction(type="keyboard_tap", keys=["space"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(a=1), 0.0)
        mapper.process(snapshot(a=1), 0.1)
        self.assertEqual(backend.events, [("key_tap", ("space",))])

    def test_hold_releases_on_missing_signal(self) -> None:
        rule = MappingRule(
            source="fused.a",
            comparator="truthy",
            action=MappingAction(type="keyboard_hold", keys=["shift"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(a=True), 0.0)
        mapper.process(snapshot(), 0.1)
        self.assertEqual(backend.events, [("key_down", "shift"), ("key_up", "shift")])

    def test_overlapping_holds_share_key_until_all_rules_release(self) -> None:
        rules = [
            MappingRule(
                id="one",
                source="fused.a",
                comparator="truthy",
                action=MappingAction(type="keyboard_hold", keys=["ctrl"]),
            ),
            MappingRule(
                id="two",
                source="fused.b",
                comparator="truthy",
                action=MappingAction(type="keyboard_hold", keys=["ctrl"]),
            ),
        ]
        mapper, backend = self.mapper_with(rules)
        mapper.process(snapshot(a=True, b=True), 0.0)
        mapper.process(snapshot(a=False, b=True), 0.1)
        mapper.process(snapshot(a=False, b=False), 0.2)
        self.assertEqual(backend.events, [("key_down", "ctrl"), ("key_up", "ctrl")])

    def test_debounce_delays_activation(self) -> None:
        rule = MappingRule(
            source="fused.a",
            comparator="truthy",
            debounce_ms=100,
            action=MappingAction(type="keyboard_tap", keys=["enter"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(a=True), 0.0)
        mapper.process(snapshot(a=True), 0.05)
        mapper.process(snapshot(a=True), 0.11)
        self.assertEqual(backend.events, [("key_tap", ("enter",))])

    def test_wrist_gesture_bypasses_debounce_and_uses_action_cooldown(self) -> None:
        rule = MappingRule(
            source="fused.wrist_roll_right_detected",
            comparator="truthy",
            debounce_ms=1000,
            action=MappingAction(type="keyboard_tap", keys=["r"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(wrist_roll_right_detected=True), 0.0)
        mapper.process(snapshot(wrist_roll_right_detected=False), 0.01)
        mapper.process(snapshot(wrist_roll_right_detected=True), GESTURE_COOLDOWN_SEC - 0.01)
        mapper.process(snapshot(wrist_roll_right_detected=False), GESTURE_COOLDOWN_SEC)
        mapper.process(snapshot(wrist_roll_right_detected=True), GESTURE_COOLDOWN_SEC + 0.01)
        self.assertEqual(backend.events, [("key_tap", ("r",)), ("key_tap", ("r",))])

    def test_wrist_gesture_cooldowns_are_per_gesture_class(self) -> None:
        rules = [
            MappingRule(
                id="roll",
                source="fused.wrist_roll_right_detected",
                comparator="truthy",
                action=MappingAction(type="keyboard_tap", keys=["r"]),
            ),
            MappingRule(
                id="pitch",
                source="fused.wrist_pitch_up_detected",
                comparator="truthy",
                action=MappingAction(type="keyboard_tap", keys=["p"]),
            ),
        ]
        mapper, backend = self.mapper_with(rules)
        mapper.process(snapshot(wrist_roll_right_detected=True, wrist_pitch_up_detected=True), 0.0)
        self.assertEqual(backend.events, [("key_tap", ("r",)), ("key_tap", ("p",))])

    def test_learned_wrist_motion_mapping_uses_action_cooldown(self) -> None:
        rule = MappingRule(
            source="fused.wrist_motion",
            comparator="eq",
            threshold="roll_right_then_neutral",
            action=MappingAction(type="keyboard_tap", keys=["n"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(wrist_motion="roll_right_then_neutral"), 0.0)
        mapper.process(snapshot(wrist_motion="none"), 0.01)
        mapper.process(snapshot(wrist_motion="roll_right_then_neutral"), 0.2)
        self.assertEqual(backend.events, [("key_tap", ("n",))])

    def test_repeat_action_uses_interval(self) -> None:
        rule = MappingRule(
            source="fused.a",
            comparator="truthy",
            action=MappingAction(type="keyboard_repeat", keys=["x"], interval_ms=100),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(a=True), 0.0)
        mapper.process(snapshot(a=True), 0.05)
        mapper.process(snapshot(a=True), 0.11)
        self.assertEqual(backend.events, [("key_tap", ("x",)), ("key_tap", ("x",))])

    def test_mouse_move_scales_by_elapsed_time(self) -> None:
        rule = MappingRule(
            source="fused.a",
            comparator="truthy",
            action=MappingAction(type="mouse_move", speed_x=100, speed_y=-50),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(a=True), 0.0)
        mapper.process(snapshot(a=True), 0.1)
        self.assertEqual(backend.events, [("move", 10, -5)])

    def test_mouse_move_can_follow_angle_delta_source(self) -> None:
        rule = MappingRule(
            source="fused.active",
            comparator="truthy",
            action=MappingAction(
                type="mouse_move",
                delta_x_source="fused.roll",
                delta_x_scale=-4,
                delta_x_angle=True,
            ),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(active=True, roll=0), 0.0)
        mapper.process(snapshot(active=True, roll=350), 0.1)
        mapper.process(snapshot(active=True, roll=10), 0.2)
        self.assertEqual(backend.events, [("move", 40, 0), ("move", -80, 0)])

    def test_action_can_center_cursor_before_firing(self) -> None:
        rule = MappingRule(
            source="fused.a",
            comparator="truthy",
            action=MappingAction(type="mouse_scroll", scroll_y=3, center_before=True),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(a=True), 0.0)
        self.assertEqual(backend.events, [("move_absolute", 959, 539), ("scroll", 0, 3)])

    def test_switch_tabs_mapping_uses_relative_z_change_and_releases_alt(self) -> None:
        rules = [
            MappingRule(
                id="switchtabs2_alt_hold",
                source="hands.left.gesture",
                comparator="eq",
                threshold="closed_fist",
                action=MappingAction(type="keyboard_hold", keys=["alt"]),
            ),
            MappingRule(
                id="switchtabs2_cycle_forward",
                source="hands.right.z_mm",
                comparator="delta_decrease",
                threshold=90,
                gate_source="hands.left.gesture",
                gate_comparator="eq",
                gate_threshold="closed_fist",
                recognition_label="Alt+Tab recognised",
                action=MappingAction(type="keyboard_tap", keys=["tab"]),
            ),
            MappingRule(
                id="switchtabs2_cycle_backward",
                source="hands.right.z_mm",
                comparator="delta_increase",
                threshold=90,
                gate_source="hands.left.gesture",
                gate_comparator="eq",
                gate_threshold="closed_fist",
                recognition_label="Alt+Tab recognised",
                action=MappingAction(type="keyboard_tap", keys=["shift", "tab"]),
            ),
        ]
        mapper, backend = self.mapper_with(rules)
        mapper.process(hand_snapshot({"right_hand_z_mm": 700}, left_gesture="closed_fist", right_visible=True), 0.0)
        mapper.process(hand_snapshot({"right_hand_z_mm": 650}, left_gesture="closed_fist", right_visible=True), 0.1)
        mapper.process(hand_snapshot({"right_hand_z_mm": 590}, left_gesture="closed_fist", right_visible=True), 0.2)
        mapper.process(hand_snapshot({"right_hand_z_mm": 620}, left_gesture="closed_fist", right_visible=True), 0.3)
        mapper.process(hand_snapshot({"right_hand_z_mm": 710}, left_gesture="closed_fist", right_visible=True), 0.4)
        mapper.process(hand_snapshot({"right_hand_z_mm": 710}, left_gesture="open_palm", right_visible=True), 0.5)
        self.assertEqual(
            backend.events,
            [
                ("key_down", "alt"),
                ("key_tap", ("tab",)),
                ("key_tap", ("shift", "tab")),
                ("key_up", "alt"),
            ],
        )
        self.assertEqual(mapper.last_recognition(max_age_s=1.0, now_s=0.4), "Alt+Tab recognised")

    def test_relative_z_mapping_is_gated_by_left_fist(self) -> None:
        rule = MappingRule(
            source="hands.right.z_mm",
            comparator="delta_decrease",
            threshold=90,
            gate_source="hands.left.gesture",
            gate_comparator="eq",
            gate_threshold="closed_fist",
            action=MappingAction(type="keyboard_tap", keys=["tab"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(hand_snapshot({"right_hand_z_mm": 700}, left_gesture="open_palm", right_visible=True), 0.0)
        mapper.process(hand_snapshot({"right_hand_z_mm": 540}, left_gesture="open_palm", right_visible=True), 0.1)
        mapper.process(hand_snapshot({"right_hand_z_mm": 520}, left_gesture="closed_fist", right_visible=True), 0.2)
        mapper.process(hand_snapshot({"right_hand_z_mm": 440}, left_gesture="closed_fist", right_visible=True), 0.3)
        mapper.process(hand_snapshot({"right_hand_z_mm": 340}, left_gesture="closed_fist", right_visible=True), 0.4)
        self.assertEqual(backend.events, [("key_tap", ("tab",))])

    def test_rule_supports_multiple_required_conditions(self) -> None:
        rule = MappingRule(
            source="fused.wrist_roll",
            comparator="gt",
            threshold=20,
            conditions=[
                MappingCondition(source="hands.left.gesture", comparator="eq", threshold="closed_fist"),
                MappingCondition(source="hands.right.gesture", comparator="eq", threshold="closed_fist"),
            ],
            action=MappingAction(type="keyboard_tap", keys=["cmd", "shift", "s"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(
            {
                "input_dict": {"wrist_roll": 25},
                "hand_state": {
                    "left": {"visible": True, "gesture": "closed_fist"},
                    "right": {"visible": True, "gesture": "open_palm"},
                },
            },
            0.0,
        )
        mapper.process(
            {
                "input_dict": {"wrist_roll": 25},
                "hand_state": {
                    "left": {"visible": True, "gesture": "closed_fist"},
                    "right": {"visible": True, "gesture": "closed_fist"},
                },
            },
            0.1,
        )
        self.assertEqual(backend.events, [("key_tap", ("cmd", "shift", "s"))])

    def test_modifier_condition_can_hold_output_key_for_main_action(self) -> None:
        rule = MappingRule(
            source="hands.right.z_mm",
            comparator="delta_decrease",
            threshold=30,
            conditions=[
                MappingCondition(
                    source="hands.left.gesture",
                    comparator="eq",
                    threshold="closed_fist",
                    output_keys=["alt"],
                ),
            ],
            action=MappingAction(type="keyboard_tap", keys=["tab"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(hand_snapshot({"right_hand_z_mm": 700}, left_gesture="closed_fist", right_visible=True), 0.0)
        mapper.process(hand_snapshot({"right_hand_z_mm": 660}, left_gesture="closed_fist", right_visible=True), 0.1)
        mapper.process(hand_snapshot({"right_hand_z_mm": 660}, left_gesture="open_palm", right_visible=True), 0.2)
        self.assertEqual(backend.events, [("key_down", "alt"), ("key_tap", ("tab",)), ("key_up", "alt")])

    def test_two_modifier_conditions_can_hold_two_output_keys(self) -> None:
        rule = MappingRule(
            source="fused.wrist_roll",
            comparator="gt",
            threshold=20,
            conditions=[
                MappingCondition(
                    source="hands.left.gesture",
                    comparator="eq",
                    threshold="closed_fist",
                    output_keys=["cmd"],
                ),
                MappingCondition(
                    source="hands.right.gesture",
                    comparator="eq",
                    threshold="closed_fist",
                    output_keys=["shift"],
                ),
            ],
            action=MappingAction(type="keyboard_tap", keys=["s"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(
            {
                "input_dict": {"wrist_roll": 25},
                "hand_state": {
                    "left": {"visible": True, "gesture": "closed_fist"},
                    "right": {"visible": True, "gesture": "closed_fist"},
                },
            },
            0.0,
        )
        mapper.process(
            {
                "input_dict": {"wrist_roll": 0},
                "hand_state": {
                    "left": {"visible": True, "gesture": "open_palm"},
                    "right": {"visible": True, "gesture": "open_palm"},
                },
            },
            0.1,
        )
        self.assertEqual(
            backend.events,
            [
                ("key_down", "cmd"),
                ("key_down", "shift"),
                ("key_tap", ("s",)),
                ("key_up", "cmd"),
                ("key_up", "shift"),
            ],
        )

    def test_mouse_absolute_can_follow_live_signal_sources(self) -> None:
        rule = MappingRule(
            source="fused.right_hand_z_mm",
            comparator="lt",
            threshold=40,
            action=MappingAction(
                type="mouse_absolute",
                continuous=True,
                absolute_x_source="fused.right_hand_x",
                absolute_y_source="fused.right_hand_y",
            ),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(right_hand_z_mm=35, right_hand_x=0.25, right_hand_y=0.75), 0.0)
        self.assertEqual(backend.events, [("move_absolute", 479, 809)])

    def test_hand_z_signal_requires_visible_hand(self) -> None:
        hidden = SignalCatalog.flatten(hand_snapshot({"right_hand_z_mm": 700}, right_visible=False))
        visible = SignalCatalog.flatten(hand_snapshot({"right_hand_z_mm": 700}, right_visible=True))
        self.assertIsNone(hidden["hands.right.z_mm"].value)
        self.assertEqual(visible["hands.right.z_mm"].value, 700)


class MappingConfigTests(unittest.TestCase):
    def test_default_config_includes_3dviewer_profile(self) -> None:
        config = default_mapping_config()
        self.assertIn(THREEDVIEWER_PROFILE_NAME, config.profile_names())
        self.assertIn(WINDOWS_3D_VIEWER_PROFILE_NAME, config.profile_names())
        profile = next(profile for profile in config.profiles if profile.name == THREEDVIEWER_PROFILE_NAME)
        self.assertGreaterEqual(len(profile.mappings), 8)
        windows_profile = next(profile for profile in config.profiles if profile.name == WINDOWS_3D_VIEWER_PROFILE_NAME)
        self.assertEqual(len(windows_profile.mappings), len(profile.mappings))

    def test_loaded_legacy_config_gets_3dviewer_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input_mappings.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "enabled_on_start": False,
                        "active_profile": "Default",
                        "profiles": [{"name": "Default", "mappings": []}],
                    }
                ),
                encoding="utf-8",
            )
            loaded, error = load_mapping_config(path)
            self.assertIsNone(error)
            self.assertIn(THREEDVIEWER_PROFILE_NAME, loaded.profile_names())
            self.assertIn(WINDOWS_3D_VIEWER_PROFILE_NAME, loaded.profile_names())
            self.assertEqual(loaded.active_profile, "Default")

    def test_save_and_load_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input_mappings.json"
            config = MappingConfig()
            config.active().mappings.append(
                MappingRule(
                    source="fused.a",
                    conditions=[MappingCondition(source="fused.b", comparator="truthy", output_keys=["alt"])],
                    action=MappingAction(type="keyboard_tap", keys=["space"], center_before=True),
                )
            )
            save_mapping_config(config, path)
            loaded, error = load_mapping_config(path)
            self.assertIsNone(error)
            self.assertEqual(loaded.active().mappings[0].source, "fused.a")
            self.assertEqual(loaded.active().mappings[0].conditions[0].source, "fused.b")
            self.assertEqual(loaded.active().mappings[0].conditions[0].output_keys, ["alt"])
            self.assertTrue(loaded.active().mappings[0].action.center_before)

    def test_3dviewer_profile_orbits_with_left_fist_and_right_hand(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)
        mapper.process(hand_snapshot({}, left_gesture="closed_fist", right_visible=True), 0.0)
        mapper.process(hand_snapshot({}, left_gesture="closed_fist", right_visible=True), 0.13)
        self.assertEqual(
            backend.events,
            [
                ("move_absolute", 959, 539),
                ("mouse_down", "left"),
                ("move_absolute", 959, 539),
            ],
        )

    def test_3dviewer_profile_does_not_orbit_without_left_fist(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)
        mapper.process(hand_snapshot({}, right_visible=True), 0.0)
        self.assertEqual(backend.events, [])

    def test_3dviewer_profile_pans_with_right_fist(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)
        mapper.process(
            {
                "input_dict": {},
                "hand_state": {
                    "right": {
                        "visible": True,
                        "x": 0.25,
                        "y": 0.75,
                        "score": 1.0,
                        "gesture": "closed_fist",
                    }
                },
            },
            0.0,
        )
        mapper.process(
            {
                "input_dict": {},
                "hand_state": {
                    "right": {
                        "visible": True,
                        "x": 0.25,
                        "y": 0.75,
                        "score": 1.0,
                        "gesture": "closed_fist",
                    }
                },
            },
            0.13,
        )
        self.assertEqual(
            backend.events,
            [
                ("move_absolute", 959, 539),
                ("mouse_down", "middle"),
                ("move_absolute", 479, 809),
            ],
        )

    def test_3dviewer_profile_zooms_with_pointing_depth_change(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)
        mapper.process(hand_snapshot({"right_hand_z_mm": 700}, right_visible=True), 0.0)
        mapper.process(hand_snapshot({"right_hand_z_mm": 600}, right_visible=True), 0.1)
        self.assertNotIn(("scroll", 0, 1), backend.events)

        pointing_snapshot = {
            "input_dict": {"right_hand_z_mm": 600},
            "hand_state": {
                "right": {
                    "visible": True,
                    "x": 0.5,
                    "y": 0.5,
                    "score": 1.0,
                    "gesture": "index_finger_up",
                }
            },
        }
        mapper.process(pointing_snapshot, 0.2)
        pointing_snapshot["input_dict"] = {"right_hand_z_mm": 570}
        mapper.process(pointing_snapshot, 0.3)
        self.assertIn(("scroll", 0, 8), backend.events)

    def test_3dviewer_profile_zooms_with_two_open_hands(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        two_open_hands_snapshot = {
            "input_dict": {"both_hands_distance": 0.25},
            "hand_state": {
                "left": {"visible": True, "gesture": "open_palm"},
                "right": {"visible": True, "gesture": "open_palm"},
            },
        }
        mapper.process(two_open_hands_snapshot, 0.0)
        self.assertNotIn(("scroll", 0, 8), backend.events)

        two_open_hands_snapshot["input_dict"] = {"both_hands_distance": 0.39}
        mapper.process(two_open_hands_snapshot, 0.1)
        self.assertIn(("scroll", 0, 8), backend.events)

        two_open_hands_snapshot["input_dict"] = {"both_hands_distance": 0.23}
        mapper.process(two_open_hands_snapshot, 0.2)
        self.assertIn(("scroll", 0, -8), backend.events)

    def test_3dviewer_two_hand_zoom_requires_open_palms(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        snapshot_with_fist = {
            "input_dict": {"both_hands_distance": 0.25},
            "hand_state": {
                "left": {"visible": True, "gesture": "closed_fist"},
                "right": {"visible": True, "gesture": "open_palm"},
            },
        }
        mapper.process(snapshot_with_fist, 0.0)
        snapshot_with_fist["input_dict"] = {"both_hands_distance": 0.45}
        mapper.process(snapshot_with_fist, 0.1)
        self.assertNotIn(("scroll", 0, 8), backend.events)

    def test_3dviewer_profile_points_without_auto_clicking(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)
        pointing_snapshot = {
            "input_dict": {},
            "hand_state": {
                "right": {
                    "visible": True,
                    "x": 0.5,
                    "y": 0.5,
                    "score": 1.0,
                    "gesture": "index_finger_up",
                }
            },
        }
        mapper.process(pointing_snapshot, 0.0)
        mapper.process(pointing_snapshot, 0.1)
        mapper.process(pointing_snapshot, 0.4)
        self.assertNotIn(("mouse_click", "left", 1), backend.events)
        self.assertIn(("move_absolute", 959, 539), backend.events)

    def test_3dviewer_profile_rotates_with_wrist_roll(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        mapper.process(
            snapshot(wrist_roll=0, wrist_roll_abs_delta=12, wrist_roll_delta=0, wrist_roll_dominant=True),
            0.0,
        )
        mapper.process(
            snapshot(wrist_roll=-22, wrist_roll_abs_delta=22, wrist_roll_delta=-22, wrist_roll_dominant=True),
            0.1,
        )
        mapper.process(
            snapshot(wrist_roll=-44, wrist_roll_abs_delta=44, wrist_roll_delta=-44, wrist_roll_dominant=True),
            0.2,
        )
        mapper.process(
            snapshot(wrist_roll=-22, wrist_roll_abs_delta=22, wrist_roll_delta=22, wrist_roll_dominant=True),
            0.3,
        )
        mapper.process(
            snapshot(wrist_roll=-22, wrist_roll_abs_delta=0, wrist_roll_delta=0, wrist_roll_dominant=False),
            0.4,
        )

        self.assertIn(("mouse_down", "left"), backend.events)
        self.assertIn(("move_absolute", 959, 539), backend.events)
        self.assertIn(("move", 88, 0), backend.events)
        self.assertTrue(any(event[0] == "move" and event[1] < 0 for event in backend.events))
        self.assertIn(("mouse_up", "left"), backend.events)

    def test_windows_3d_viewer_profile_uses_centered_orbit_and_zoom(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = WINDOWS_3D_VIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)
        mapper.process(hand_snapshot({}, left_gesture="closed_fist", right_visible=True), 0.0)
        mapper.process(hand_snapshot({}, left_gesture="closed_fist", right_visible=True), 0.13)
        self.assertEqual(
            backend.events,
            [
                ("move_absolute", 959, 539),
                ("mouse_down", "left"),
                ("move_absolute", 959, 539),
            ],
        )

        mapper.process(hand_snapshot({}, left_gesture="open_palm", right_visible=False), 0.2)
        backend.events.clear()
        two_open_hands_snapshot = {
            "input_dict": {"both_hands_distance": 0.25},
            "hand_state": {
                "left": {"visible": True, "gesture": "open_palm"},
                "right": {"visible": True, "gesture": "open_palm"},
            },
        }
        mapper.process(two_open_hands_snapshot, 0.3)
        two_open_hands_snapshot["input_dict"] = {"both_hands_distance": 0.39}
        mapper.process(two_open_hands_snapshot, 0.4)
        self.assertEqual(backend.events, [("move_absolute", 959, 539), ("scroll", 0, 8)])

    def test_invalid_config_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input_mappings.json"
            path.write_text(json.dumps({"version": 1, "profiles": [{"mappings": [{"action": {"type": "bad"}}]}]}))
            loaded, error = load_mapping_config(path)
            self.assertIsNotNone(error)
            self.assertEqual(loaded.active().mappings, [])


if __name__ == "__main__":
    unittest.main()
