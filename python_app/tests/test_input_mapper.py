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
    GTA_VICE_CITY_PROFILE_NAME,
    GTA_VICE_CITY_PROCESS_CANDIDATES,
    InputMapper,
    MappingAction,
    MappingCondition,
    MappingConfig,
    MappingRule,
    THREEDVIEWER_PROFILE_NAME,
    THREEDVIEWER_ZOOM_SCROLL_INTERVAL_MS,
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


def gesture_pair_snapshot(left_gesture: str | None, right_gesture: str | None) -> dict[str, object]:
    return {
        "input_dict": {},
        "hand_state": {
            "left": {
                "visible": left_gesture is not None,
                "x": 0.4,
                "y": 0.5,
                "score": 1.0 if left_gesture is not None else 0.0,
                "gesture": left_gesture or "none",
            },
            "right": {
                "visible": right_gesture is not None,
                "x": 0.6,
                "y": 0.5,
                "score": 1.0 if right_gesture is not None else 0.0,
                "gesture": right_gesture or "none",
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

    def test_mouse_move_drag_holds_button_during_movement_and_releases_on_exit(self) -> None:
        rule = MappingRule(
            source="fused.active",
            comparator="truthy",
            action=MappingAction(
                type="mouse_move",
                drag_button="left",
                delta_x_source="fused.position",
                delta_x_scale=4,
                center_before=True,
            ),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(active=True, position=0), 0.0)
        mapper.process(snapshot(active=True, position=3), 0.1)
        mapper.process(snapshot(active=False, position=3), 0.2)
        self.assertEqual(
            backend.events,
            [
                ("move_absolute", 959, 539),
                ("mouse_down", "left"),
                ("move", 12, 0),
                ("mouse_up", "left"),
            ],
        )

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
        self.assertIn(GTA_VICE_CITY_PROFILE_NAME, config.profile_names())
        profile = next(profile for profile in config.profiles if profile.name == THREEDVIEWER_PROFILE_NAME)
        self.assertGreaterEqual(len(profile.mappings), 8)
        windows_profile = next(profile for profile in config.profiles if profile.name == WINDOWS_3D_VIEWER_PROFILE_NAME)
        self.assertEqual(len(windows_profile.mappings), 3)
        for viewer_profile in (profile, windows_profile):
            zoom_rules = [rule for rule in viewer_profile.mappings if rule.action.type == "mouse_scroll"]
            self.assertEqual(len(zoom_rules), 2)
            self.assertEqual({rule.recognition_label for rule in zoom_rules}, {"zoom_in", "zoom_out"})
            self.assertTrue(all(abs(rule.action.scroll_y) == 1 for rule in zoom_rules))
            self.assertTrue(all(rule.action.interval_ms == THREEDVIEWER_ZOOM_SCROLL_INTERVAL_MS for rule in zoom_rules))
            self.assertTrue(all(rule.source == "fused.two_hand_zoom_direction" for rule in zoom_rules))
            self.assertEqual({rule.threshold for rule in zoom_rules}, {"in", "out"})
            if viewer_profile.name == THREEDVIEWER_PROFILE_NAME:
                wrist_drag_rules = [
                    rule
                    for rule in viewer_profile.mappings
                    if rule.source == "fused.wrist_sample_rotate_active"
                ]
                self.assertEqual(len(wrist_drag_rules), 1)
                self.assertEqual(wrist_drag_rules[0].action.type, "mouse_move")
                self.assertEqual(wrist_drag_rules[0].action.drag_button, "left")
                self.assertTrue(wrist_drag_rules[0].action.center_before)
        windows_wrist_rule = next(
            rule
            for rule in windows_profile.mappings
            if rule.id == "windows3dviewer_wrist_roll_rotate"
        )
        self.assertEqual(windows_wrist_rule.source, "fused.wrist_roll_rotate_active")
        self.assertEqual(windows_wrist_rule.action.speed_x_source, "fused.wrist_roll_rotate_velocity_dps")
        self.assertEqual(windows_wrist_rule.action.foreground_process, "3DViewer.exe|View3D.exe")
        self.assertFalse(windows_wrist_rule.action.hide_cursor_during_action)
        self.assertFalse(windows_wrist_rule.action.restore_cursor_after_action)
        self.assertEqual(windows_wrist_rule.action.pointer_session_warmup_ms, 40)
        self.assertEqual(windows_wrist_rule.action.pointer_mode, "touch")

    def test_gta_vice_city_profile_matches_requested_controls_and_targets_game(self) -> None:
        profile = next(
            profile
            for profile in default_mapping_config().profiles
            if profile.name == GTA_VICE_CITY_PROFILE_NAME
        )
        self.assertEqual(len(profile.mappings), 7)
        self.assertEqual(
            {rule.id for rule in profile.mappings},
            {
                "gtavc_right_hand_forward",
                "gtavc_right_hand_backward",
                "gtavc_left_palm_turn_right",
                "gtavc_left_palm_turn_left",
                "gtavc_right_palm_up_jump",
                "gtavc_wrist_clockwise_next_weapon",
                "gtavc_wrist_counterclockwise_previous_weapon",
            },
        )
        self.assertTrue(all(rule.action.foreground_process == GTA_VICE_CITY_PROCESS_CANDIDATES for rule in profile.mappings))
        self.assertTrue(all(not rule.action.activate_foreground_process for rule in profile.mappings))
        sources = {rule.id: rule.source for rule in profile.mappings}
        self.assertEqual(
            sources["gtavc_wrist_clockwise_next_weapon"],
            "fused.wrist_weapon_clockwise_detected",
        )
        self.assertEqual(
            sources["gtavc_wrist_counterclockwise_previous_weapon"],
            "fused.wrist_weapon_counterclockwise_detected",
        )

    def test_gta_training_applies_personalized_direction_and_threshold(self) -> None:
        mapper = InputMapper(FakeInputBackend(), default_mapping_config())
        mapper.apply_gta_training(
            {
                "rule_thresholds": {
                    "gtavc_right_hand_forward": {"signed_threshold": -85.0},
                    "gtavc_left_palm_turn_right": {"signed_threshold": 0.045},
                }
            }
        )
        profile = next(profile for profile in mapper.config.profiles if profile.name == GTA_VICE_CITY_PROFILE_NAME)
        rules = {rule.id: rule for rule in profile.mappings}

        self.assertEqual(rules["gtavc_right_hand_forward"].comparator, "lt")
        self.assertEqual(rules["gtavc_right_hand_forward"].threshold, -85.0)
        self.assertEqual(rules["gtavc_left_palm_turn_right"].comparator, "gt")
        self.assertAlmostEqual(rules["gtavc_left_palm_turn_right"].threshold, 0.045)

    def test_gta_vice_city_right_hand_depth_walks_forward_and_reverse(self) -> None:
        backend = FakeInputBackend()
        backend.available_target_processes.add("Mss32.exe")
        backend.active_foreground_process = "Mss32.exe"
        config = default_mapping_config()
        config.active_profile = GTA_VICE_CITY_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        mapper.process(snapshot(right_hand_depth_offset_mm=150), 0.0)
        mapper.process(snapshot(right_hand_depth_offset_mm=150), 0.09)
        mapper.process(snapshot(right_hand_depth_offset_mm=0), 0.18)
        mapper.process(snapshot(right_hand_depth_offset_mm=0), 0.27)
        mapper.process(snapshot(right_hand_depth_offset_mm=-150), 0.36)
        mapper.process(snapshot(right_hand_depth_offset_mm=-150), 0.45)

        self.assertIn(("key_down", "w"), backend.events)
        self.assertIn(("key_down", "space"), backend.events)
        self.assertIn(("key_up", "w"), backend.events)
        self.assertIn(("key_up", "space"), backend.events)
        self.assertIn(("key_down", "s"), backend.events)
        self.assertTrue(any(event[0] == "pointer_session_begin" for event in backend.events))
        self.assertFalse(any(event[0].startswith("mouse_") or event[0] in {"move", "move_absolute"} for event in backend.events))

    def test_gta_vice_city_open_palms_turn_and_jump(self) -> None:
        backend = FakeInputBackend()
        backend.available_target_processes.add("Mss32.exe")
        backend.active_foreground_process = "Mss32.exe"
        config = default_mapping_config()
        config.active_profile = GTA_VICE_CITY_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        right_turn = gesture_pair_snapshot("open_palm", "none")
        right_turn["input_dict"] = {"left_palm_horizontal_offset": 0.10, "right_palm_vertical_offset": 0.0}
        mapper.process(right_turn, 0.0)
        mapper.process(right_turn, 0.08)
        neutral = gesture_pair_snapshot("open_palm", "open_palm")
        neutral["input_dict"] = {"left_palm_horizontal_offset": 0.0, "right_palm_vertical_offset": 0.0}
        mapper.process(neutral, 0.16)
        mapper.process(neutral, 0.24)
        jump = gesture_pair_snapshot("open_palm", "open_palm")
        jump["input_dict"] = {"left_palm_horizontal_offset": 0.0, "right_palm_vertical_offset": 0.13}
        mapper.process(jump, 0.32)
        mapper.process(jump, 0.41)

        self.assertIn(("key_down", "d"), backend.events)
        self.assertIn(("key_up", "d"), backend.events)
        self.assertIn(("key_tap", ("ctrl",)), backend.events)
        self.assertFalse(any(event[0].startswith("mouse_") or event[0] in {"move", "move_absolute"} for event in backend.events))

    def test_gta_vice_city_wrist_rotations_swap_weapons_one_step_each(self) -> None:
        backend = FakeInputBackend()
        backend.available_target_processes.add("Mss32.exe")
        backend.active_foreground_process = "Mss32.exe"
        config = default_mapping_config()
        config.active_profile = GTA_VICE_CITY_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        mapper.process(snapshot(wrist_weapon_clockwise_detected=True, wrist_weapon_counterclockwise_detected=False), 0.0)
        mapper.process(snapshot(wrist_weapon_clockwise_detected=False, wrist_weapon_counterclockwise_detected=False), 0.1)
        mapper.process(snapshot(wrist_weapon_clockwise_detected=False, wrist_weapon_counterclockwise_detected=True), 0.8)

        self.assertIn(("scroll", 0, 1), backend.events)
        self.assertIn(("scroll", 0, -1), backend.events)
        self.assertFalse(any(event[0] in {"move", "move_absolute", "mouse_click", "mouse_down", "mouse_up"} for event in backend.events))

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

    def test_3dviewer_profile_smoothly_zooms_with_recorded_open_palm_gestures(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        two_open_hands_snapshot = {
            "input_dict": {"two_hand_zoom_direction": "none"},
            "hand_state": {
                "left": {"visible": True, "gesture": "open_palm"},
                "right": {"visible": True, "gesture": "open_palm"},
            },
        }
        mapper.process(two_open_hands_snapshot, 0.0)
        for now_s in (0.1, 0.25, 0.40):
            two_open_hands_snapshot["input_dict"] = {"two_hand_zoom_direction": "in"}
            mapper.process(two_open_hands_snapshot, now_s)
        for now_s in (0.55, 0.70, 0.85):
            two_open_hands_snapshot["input_dict"] = {"two_hand_zoom_direction": "out"}
            mapper.process(two_open_hands_snapshot, now_s)

        scroll_events = [event for event in backend.events if event[0] == "scroll"]
        self.assertEqual(scroll_events, [("scroll", 0, 1)] * 3 + [("scroll", 0, -1)] * 3)
        self.assertNotIn(("scroll", 0, 8), backend.events)
        self.assertNotIn(("scroll", 0, -8), backend.events)
        self.assertIn(("move_absolute", 959, 539), backend.events)
        self.assertEqual(mapper.last_recognition(max_age_s=1.0, now_s=0.85), "zoom_out")

    def test_3dviewer_recorded_zoom_requires_two_open_palms(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)
        snapshot_with_fist = {
            "input_dict": {"two_hand_zoom_direction": "in"},
            "hand_state": {
                "left": {"visible": True, "gesture": "closed_fist"},
                "right": {"visible": True, "gesture": "open_palm"},
            },
        }
        mapper.process(snapshot_with_fist, 0.0)
        mapper.process(snapshot_with_fist, 0.1)
        self.assertFalse(any(event[0] == "scroll" for event in backend.events))

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

    def test_3dviewer_profile_smoothly_rotates_with_recorded_wristband_gestures(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = THREEDVIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        mapper.process(
            snapshot(
                wrist_sample_rotate_active=False,
                wrist_sample_rotate_direction="none",
                wrist_sample_rotate_position=0,
            ),
            0.0,
        )
        mapper.process(
            snapshot(
                wrist_sample_rotate_active=True,
                wrist_sample_rotate_direction="right",
                wrist_sample_rotate_position=3,
            ),
            0.1,
        )
        mapper.process(
            snapshot(
                wrist_sample_rotate_active=True,
                wrist_sample_rotate_direction="right",
                wrist_sample_rotate_position=7,
            ),
            0.2,
        )
        mapper.process(
            snapshot(
                wrist_sample_rotate_active=False,
                wrist_sample_rotate_direction="none",
                wrist_sample_rotate_position=7,
            ),
            0.3,
        )
        mapper.process(
            snapshot(
                wrist_sample_rotate_active=True,
                wrist_sample_rotate_direction="left",
                wrist_sample_rotate_position=3,
            ),
            0.4,
        )
        mapper.process(
            snapshot(
                wrist_sample_rotate_active=True,
                wrist_sample_rotate_direction="left",
                wrist_sample_rotate_position=-2,
            ),
            0.5,
        )

        self.assertIn(("mouse_down", "left"), backend.events)
        self.assertIn(("move_absolute", 959, 539), backend.events)
        self.assertIn(("move", 16, 0), backend.events)
        self.assertTrue(any(event[0] == "move" and event[1] < 0 for event in backend.events))
        self.assertIn(("mouse_up", "left"), backend.events)
        self.assertTrue(all(abs(event[1]) <= 18 for event in backend.events if event[0] == "move"))

    def test_windows_3d_viewer_profile_ignores_camera_cursor_rules(self) -> None:
        backend = FakeInputBackend()
        config = default_mapping_config()
        config.active_profile = WINDOWS_3D_VIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)
        mapper.process(hand_snapshot({}, left_gesture="closed_fist", right_visible=True), 0.0)
        mapper.process(hand_snapshot({}, left_gesture="closed_fist", right_visible=True), 0.13)
        self.assertEqual(backend.events, [])

    def test_windows_3d_viewer_wrist_roll_right_moves_positive_x(self) -> None:
        backend = FakeInputBackend()
        backend.available_target_processes.add("3DViewer.exe")
        config = default_mapping_config()
        config.active_profile = WINDOWS_3D_VIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        roll_snapshot = {
            "wrist_roll_rotate_active": True,
            "wrist_roll_rotate_velocity_dps": 25.0,
        }
        mapper.process(snapshot(**roll_snapshot), 0.0)
        mapper.process(snapshot(**roll_snapshot), 0.1)
        mapper.process(snapshot(**roll_snapshot), 0.2)

        moves = [event for event in backend.events if event[0] == "pointer_session_move"]
        self.assertTrue(moves)
        self.assertTrue(all(event[2] > 0 for event in moves))

    def test_windows_3d_viewer_wrist_roll_left_moves_negative_x(self) -> None:
        backend = FakeInputBackend()
        backend.available_target_processes.add("3DViewer.exe")
        config = default_mapping_config()
        config.active_profile = WINDOWS_3D_VIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        roll_snapshot = {
            "wrist_roll_rotate_active": True,
            "wrist_roll_rotate_velocity_dps": -25.0,
        }
        mapper.process(snapshot(**roll_snapshot), 0.0)
        mapper.process(snapshot(**roll_snapshot), 0.1)
        mapper.process(snapshot(**roll_snapshot), 0.2)

        moves = [event for event in backend.events if event[0] == "pointer_session_move"]
        self.assertTrue(moves)
        self.assertTrue(all(event[2] < 0 for event in moves))

    def test_windows_3d_viewer_wrist_rotation_only_runs_while_viewer_window_exists(self) -> None:
        backend = FakeInputBackend()
        backend.active_foreground_process = "Codex.exe"
        backend.available_target_processes.clear()
        config = default_mapping_config()
        config.active_profile = WINDOWS_3D_VIEWER_PROFILE_NAME
        mapper = InputMapper(backend, config)
        mapper.set_enabled(True)

        roll_snapshot = {
            "wrist_roll_rotate_active": True,
            "wrist_roll_rotate_velocity_dps": 25.0,
        }
        mapper.process(snapshot(**roll_snapshot), 0.0)
        mapper.process(snapshot(**roll_snapshot), 0.1)
        self.assertNotIn(("mouse_down", "left"), backend.events)
        self.assertFalse(any(event[0] == "pointer_session_move" for event in backend.events))

        backend.available_target_processes.add("3DViewer.exe")
        mapper.process(snapshot(**roll_snapshot), 0.2)
        mapper.process(snapshot(**roll_snapshot), 0.3)
        self.assertTrue(any(event[0] == "pointer_session_begin" for event in backend.events))
        self.assertNotIn(("mouse_down", "left"), backend.events)

        mapper.process(snapshot(**roll_snapshot), 0.4)
        mapper.process(snapshot(**roll_snapshot), 0.5)
        self.assertIn(
            ("pointer_session_move", "windows3dviewer_wrist_roll_rotate", 10, 0),
            backend.events,
        )
        self.assertFalse(any(event[0] in {"move", "move_absolute"} for event in backend.events))

        backend.active_foreground_process = "Codex.exe"
        mapper.process(snapshot(**roll_snapshot), 0.6)
        mapper.process(snapshot(**roll_snapshot), 0.7)
        self.assertNotIn(("mouse_up", "left"), backend.events)
        self.assertFalse(any(event[0] == "pointer_session_end" for event in backend.events))
        self.assertTrue(any(event[0] == "pointer_session_move" for event in backend.events))

        backend.available_target_processes.clear()
        mapper.process(snapshot(**roll_snapshot), 0.8)
        self.assertIn(("pointer_session_end", "windows3dviewer_wrist_roll_rotate"), backend.events)

    def test_invalid_config_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input_mappings.json"
            path.write_text(json.dumps({"version": 1, "profiles": [{"mappings": [{"action": {"type": "bad"}}]}]}))
            loaded, error = load_mapping_config(path)
            self.assertIsNotNone(error)
            self.assertEqual(loaded.active().mappings, [])


if __name__ == "__main__":
    unittest.main()
