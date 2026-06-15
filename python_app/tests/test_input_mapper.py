from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from input_backend import FakeInputBackend
from input_mapper import (
    DEFAULT_PROFILE_NAME,
    GESTURE_COOLDOWN_SEC,
    GTA_VICE_CITY_PROFILE_NAME,
    InputMapper,
    MappingAction,
    MappingCondition,
    MappingConfig,
    MappingProfile,
    MappingRule,
    SignalCatalog,
    TAB_SWITCH_PROFILE_NAME,
    TAB_CURSOR_SCROLL_PROFILE_NAME,
    VIEWER_3D_PROFILE_NAME,
    WRISTBAND_MOUSE_CURSOR_PROFILE_NAME,
    default_mapping_config,
    evaluate_condition,
    load_mapping_config,
    normalize_mapping_config,
    save_mapping_config,
    gta_vice_city_profile,
    viewer_3d_profile,
    wristband_mouse_cursor_profile,
    wrist_scroll_profile,
    wrist_tab_switching_profile,
    tabs_cursor_scroll_profile,
    WRIST_SCROLL_PROFILE_NAME,
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


def voice_snapshot(transcript: str, *, voice_gate: bool) -> dict[str, object]:
    return {
        "input_dict": {"audio_dock_voice_gate": voice_gate},
        "raw_device_state": {
            "devices": {
                "audiodock": {
                    "latest_transcript": transcript,
                    "input": transcript,
                }
            }
        },
    }


def drive_voice_cheat(mapper: InputMapper, transcript: str, cheat: str, start_s: float) -> float:
    mapper.process(voice_snapshot(transcript, voice_gate=False), start_s)
    now_s = start_s + 0.01
    active_snapshot = voice_snapshot(transcript, voice_gate=True)
    mapper.process(active_snapshot, now_s)
    for _character in cheat[1:]:
        now_s += 0.251
        mapper.process(active_snapshot, now_s)
    return now_s + 0.01


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

    def test_gta_voice_cheats_require_voice_gate(self) -> None:
        mapper, backend = self.mapper_with(gta_vice_city_profile().mappings)
        now_s = drive_voice_cheat(mapper, "police", "leavemealone", 0.0)
        now_s = drive_voice_cheat(mapper, "weapons", "nuttertools", now_s)
        now_s = drive_voice_cheat(mapper, "tank", "panzer", now_s)
        drive_voice_cheat(mapper, "health", "aspirine", now_s)

        self.assertEqual(
            backend.events,
            [("key_tap", (character,)) for character in "leavemealonenuttertoolspanzeraspirine"],
        )

    def test_gta_voice_cheats_do_not_fire_without_gate(self) -> None:
        mapper, backend = self.mapper_with(gta_vice_city_profile().mappings)
        mapper.process(voice_snapshot("police", voice_gate=False), 0.0)
        mapper.process(voice_snapshot("weapons", voice_gate=False), 0.1)

        self.assertEqual(backend.events, [])

    def test_gta_voice_cheats_match_normalized_transcript_commands(self) -> None:
        mapper, backend = self.mapper_with(gta_vice_city_profile().mappings)
        now_s = drive_voice_cheat(mapper, "Police, please", "leavemealone", 0.0)
        now_s = drive_voice_cheat(mapper, "the weapons cheat", "nuttertools", now_s)
        now_s = drive_voice_cheat(mapper, "tank!", "panzer", now_s)
        drive_voice_cheat(mapper, "health?", "aspirine", now_s)

        self.assertEqual(
            backend.events,
            [("key_tap", (character,)) for character in "leavemealonenuttertoolspanzeraspirine"],
        )

    def test_gta_tank_cheat_accepts_common_transcript_variants(self) -> None:
        mapper, backend = self.mapper_with(gta_vice_city_profile().mappings)
        now_s = drive_voice_cheat(mapper, "tank", "panzer", 0.0)
        now_s = drive_voice_cheat(mapper, "thank", "panzer", now_s)
        drive_voice_cheat(mapper, "bank", "panzer", now_s)

        self.assertEqual(
            backend.events,
            [("key_tap", (character,)) for character in "panzerpanzerpanzer"],
        )

    def test_gta_health_cheat_accepts_common_transcript_variants(self) -> None:
        mapper, backend = self.mapper_with(gta_vice_city_profile().mappings)
        now_s = drive_voice_cheat(mapper, "health", "aspirine", 0.0)
        now_s = drive_voice_cheat(mapper, "help", "aspirine", now_s)
        drive_voice_cheat(mapper, "hello", "aspirine", now_s)

        self.assertEqual(
            backend.events,
            [("key_tap", (character,)) for character in "aspirineaspirineaspirine"],
        )

    def test_gta_gun_gesture_holds_left_mouse(self) -> None:
        mapper, backend = self.mapper_with(gta_vice_city_profile().mappings)
        active_snapshot = {
            "hand_state": {
                "right": {"visible": True, "gesture": "gun_gesture"},
                "left": {"visible": False, "gesture": "none"},
            }
        }
        mapper.process(active_snapshot, 0.0)
        mapper.process(active_snapshot, 0.07)
        mapper.process(
            {
                "hand_state": {
                    "right": {"visible": True, "gesture": "open_palm"},
                    "left": {"visible": False, "gesture": "none"},
                }
            },
            0.2,
        )
        mapper.process(
            {
                "hand_state": {
                    "right": {"visible": True, "gesture": "open_palm"},
                    "left": {"visible": False, "gesture": "none"},
                }
            },
            0.27,
        )

        self.assertEqual(backend.events, [("mouse_down", "left"), ("mouse_up", "left")])

    def test_gta_left_peace_sign_taps_enter_via_runtime_overlay(self) -> None:
        mapper, backend = self.mapper_with(gta_vice_city_profile().mappings)
        mapper.process(
            {
                "hand_state": {
                    "left": {"visible": True, "gesture": "peace_sign"},
                    "right": {"visible": False, "gesture": "none"},
                }
            },
            0.0,
        )
        mapper.process(
            {
                "hand_state": {
                    "left": {"visible": True, "gesture": "peace_sign"},
                    "right": {"visible": False, "gesture": "none"},
                }
            },
            0.09,
        )

        self.assertEqual(backend.events, [("key_tap", ("enter",), 250)])

    def test_keyboard_sequence_taps_one_key_per_interval(self) -> None:
        rule = MappingRule(
            source="fused.a",
            comparator="truthy",
            action=MappingAction(
                type="keyboard_sequence",
                text="abc",
                append_space=False,
                interval_ms=250,
            ),
        )
        mapper, backend = self.mapper_with([rule])

        mapper.process(snapshot(a=True), 0.0)
        mapper.process(snapshot(a=True), 0.249)
        mapper.process(snapshot(a=True), 0.250)
        mapper.process(snapshot(a=True), 0.499)
        mapper.process(snapshot(a=True), 0.500)
        mapper.process(snapshot(a=True), 0.750)

        self.assertEqual(
            backend.events,
            [
                ("key_tap", ("a",)),
                ("key_tap", ("b",)),
                ("key_tap", ("c",)),
            ],
        )

    def test_versioned_snapshot_reuses_flattened_signal_catalog(self) -> None:
        rule = MappingRule(
            source="fused.a",
            comparator="truthy",
            action=MappingAction(type="keyboard_hold", keys=["shift"]),
        )
        mapper, _backend = self.mapper_with([rule])
        versioned = {"input_dict": {"a": True}, "_signal_sequence": (1,)}
        with patch.object(SignalCatalog, "flatten", wraps=SignalCatalog.flatten) as flatten:
            mapper.process(versioned, 0.0)
            mapper.process(versioned, 0.1)
        self.assertEqual(flatten.call_count, 1)

    def test_normalize_mapping_config_migrates_legacy_windows_profile(self) -> None:
        profile = MappingProfile(
            name="Windows",
            mappings=[
                MappingRule(
                    id="wrist_tab_cycle_forward",
                    source="fused.wrist_rule_value",
                    comparator="eq",
                    threshold="rotate_right_return",
                    conditions=[
                        MappingCondition(
                            source="hands.right.z_mm",
                            comparator="lt",
                            threshold="500",
                            output_keys=["alt"],
                        )
                    ],
                    action=MappingAction(type="keyboard_tap", keys=["tab"]),
                ),
                MappingRule(
                    id="wrist_tab_cycle_backward",
                    source="fused.wrist_rule_value",
                    comparator="eq",
                    threshold="rotate_left_return",
                    conditions=[
                        MappingCondition(
                            source="hands.right.z_mm",
                            comparator="lt",
                            threshold="500",
                            output_keys=["alt"],
                        )
                    ],
                    action=MappingAction(type="keyboard_tap", keys=["shift", "tab"]),
                ),
                MappingRule(
                    id="wrist_cursor_follow_gyro",
                    source="wrist_cursor.enabled",
                    comparator="truthy",
                    conditions=[MappingCondition(source="hands.left.gesture", comparator="eq", threshold="open_palm")],
                    action=MappingAction(type="mouse_move"),
                ),
                MappingRule(
                    id="wrist_scroll_up",
                    source="wristband.gyro_x",
                    comparator="lt",
                    threshold="-4",
                    action=MappingAction(type="mouse_scroll", scroll_y=1),
                ),
                MappingRule(
                    id="wrist_scroll_down",
                    source="wristband.gyro_x",
                    comparator="gt",
                    threshold="8",
                    action=MappingAction(type="mouse_scroll", scroll_y=-1),
                ),
            ],
        )
        config = MappingConfig(active_profile="Windows", profiles=[profile, wristband_mouse_cursor_profile()])

        normalized, changed = normalize_mapping_config(config)

        self.assertTrue(changed)
        self.assertEqual(normalized.active_profile, TAB_CURSOR_SCROLL_PROFILE_NAME)
        self.assertEqual(normalized.profiles[0].name, TAB_CURSOR_SCROLL_PROFILE_NAME)
        self.assertEqual(normalized.profiles[0].mappings[0].action.keys, ["alt", "tab"])
        self.assertEqual(normalized.profiles[0].mappings[0].conditions[0].output_keys, [])
        self.assertEqual(normalized.profiles[0].mappings[1].action.keys, ["alt", "shift", "tab"])
        self.assertEqual(normalized.profiles[0].mappings[1].conditions[0].output_keys, [])

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

    def test_model_value_gesture_bypasses_debounce_and_uses_action_cooldown(self) -> None:
        rule = MappingRule(
            source="fused.model_value",
            comparator="eq",
            threshold="rotate_right",
            debounce_ms=1000,
            action=MappingAction(type="keyboard_tap", keys=["r"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(model_value="rotate_right"), 0.0)
        mapper.process(snapshot(model_value="none"), 0.01)
        mapper.process(snapshot(model_value="rotate_right"), GESTURE_COOLDOWN_SEC - 0.01)
        mapper.process(snapshot(model_value="none"), GESTURE_COOLDOWN_SEC)
        mapper.process(snapshot(model_value="rotate_right"), GESTURE_COOLDOWN_SEC + 0.01)
        self.assertEqual(backend.events, [("key_tap", ("r",)), ("key_tap", ("r",))])

    def test_model_value_cooldowns_are_per_gesture_class(self) -> None:
        rules = [
            MappingRule(
                id="roll",
                source="fused.model_value",
                comparator="eq",
                threshold="rotate_right",
                action=MappingAction(type="keyboard_tap", keys=["r"]),
            ),
            MappingRule(
                id="flick",
                source="fused.model_value",
                comparator="eq",
                threshold="flick",
                action=MappingAction(type="keyboard_tap", keys=["p"]),
            ),
        ]
        mapper, backend = self.mapper_with(rules)
        mapper.process(snapshot(model_value="rotate_right"), 0.0)
        mapper.process(snapshot(model_value="none"), 0.01)
        mapper.process(snapshot(model_value="flick"), 0.02)
        self.assertEqual(backend.events, [("key_tap", ("r",)), ("key_tap", ("p",))])

    def test_wrist_rule_value_bypasses_debounce_and_uses_gesture_cooldown(self) -> None:
        rule = MappingRule(
            source="fused.wrist_rule_value",
            comparator="eq",
            threshold="rotate_right_return",
            debounce_ms=1000,
            action=MappingAction(type="keyboard_tap", keys=["r"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(wrist_rule_value="rotate_right_return"), 0.0)
        mapper.process(snapshot(wrist_rule_value="none"), 0.01)

        self.assertEqual(backend.events, [("key_tap", ("r",))])

    def test_model_value_mapping_uses_action_cooldown(self) -> None:
        rule = MappingRule(
            source="fused.model_value",
            comparator="eq",
            threshold="wrist_circle",
            action=MappingAction(type="keyboard_tap", keys=["n"]),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(model_value="wrist_circle"), 0.0)
        mapper.process(snapshot(model_value="none"), 0.01)
        mapper.process(snapshot(model_value="wrist_circle"), 0.2)
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

    def test_mouse_move_can_follow_live_signal_sources_with_deadband_and_low_pass(self) -> None:
        rule = MappingRule(
            source="wristband.sequence",
            comparator="present",
            action=MappingAction(
                type="mouse_move",
                speed_x=100.0,
                speed_y=-200.0,
                speed_x_source="wristband.calibrated_accel_x",
                speed_y_source="wristband.calibrated_accel_y",
                move_deadband=0.5,
                move_smoothing_alpha=0.5,
            ),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(
            {"raw_device_state": {"devices": {"wristband": {"sequence": 1, "calibrated_accel": {"x": 1.0, "y": 0.0}}}}},
            0.0,
        )
        mapper.process(
            {"raw_device_state": {"devices": {"wristband": {"sequence": 2, "calibrated_accel": {"x": 0.2, "y": 0.2}}}}},
            0.1,
        )
        mapper.process(
            {"raw_device_state": {"devices": {"wristband": {"sequence": 3, "calibrated_accel": {"x": 1.0, "y": 1.0}}}}},
            0.2,
        )
        self.assertEqual(
            backend.events,
            [
                ("move", 5, 0),
                ("move", 7, -10),
            ],
        )

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

    def test_3d_viewer_orbit_hold_can_start_without_right_hand_presence(self) -> None:
        mapper, backend = self.mapper_with(viewer_3d_profile().mappings)
        mapper.process(
            {
                "hand_state": {
                    "left": {"visible": True, "gesture": "closed_fist", "x": 0.25, "y": 0.5},
                    "right": {"visible": False, "gesture": "none", "x": None, "y": None},
                }
            },
            0.0,
        )
        mapper.process(
            {
                "hand_state": {
                    "left": {"visible": True, "gesture": "open_palm", "x": 0.25, "y": 0.5},
                    "right": {"visible": False, "gesture": "none", "x": None, "y": None},
                }
            },
            0.1,
        )
        self.assertEqual(backend.events, [("mouse_down", "left"), ("mouse_up", "left")])

    def test_mouse_absolute_can_invert_smooth_and_ignore_jitter(self) -> None:
        rule = MappingRule(
            source="fused.right_hand_z_mm",
            comparator="lt",
            threshold=400,
            action=MappingAction(
                type="mouse_absolute",
                continuous=True,
                absolute_x_source="fused.right_hand_x",
                absolute_y_source="fused.right_hand_y",
                absolute_x_invert=True,
                absolute_deadband=0.03,
                absolute_smoothing_alpha=0.5,
            ),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(snapshot(right_hand_z_mm=350, right_hand_x=0.25, right_hand_y=0.50), 0.0)
        mapper.process(snapshot(right_hand_z_mm=350, right_hand_x=0.27, right_hand_y=0.51), 0.1)
        mapper.process(snapshot(right_hand_z_mm=350, right_hand_x=0.35, right_hand_y=0.50), 0.2)
        self.assertEqual(
            backend.events,
            [
                ("move_absolute", 1439, 539),
                ("move_absolute", 1343, 539),
            ],
        )

    def test_hand_z_signal_requires_visible_hand(self) -> None:
        hidden = SignalCatalog.flatten(hand_snapshot({"right_hand_z_mm": 700}, right_visible=False))
        visible = SignalCatalog.flatten(hand_snapshot({"right_hand_z_mm": 700}, right_visible=True))
        self.assertIsNone(hidden["hands.right.z_mm"].value)
        self.assertEqual(visible["hands.right.z_mm"].value, 700)

    def test_signal_catalog_exposes_model_value(self) -> None:
        signals = SignalCatalog.flatten(snapshot(model_value="flick"))

        self.assertEqual(signals["fused.model_value"].value, "flick")

    def test_signal_catalog_exposes_base_z(self) -> None:
        signals = SignalCatalog.flatten({"input_dict": {"base_z": 515.5}})

        self.assertEqual(signals["fused.base_z"].value, 515.5)

    def test_signal_catalog_exposes_calibrated_wrist_accel(self) -> None:
        signals = SignalCatalog.flatten(
            {
                "raw_device_state": {
                    "devices": {
                        "wristband": {
                            "calibrated_accel": {"x": 1.5, "y": -0.5, "z": 0.25},
                        }
                    }
                }
            }
        )
        self.assertEqual(signals["wristband.calibrated_accel_x"].value, 1.5)
        self.assertEqual(signals["wristband.calibrated_accel_y"].value, -0.5)

    def test_keyboard_text_action_types_live_signal_value(self) -> None:
        rule = MappingRule(
            source="keyboard.input",
            comparator="present",
            action=MappingAction(type="keyboard_text", text_source="keyboard.input", append_space=True),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(
            {"raw_device_state": {"devices": {"keyboard": {"input": "hello"}}}},
            0.0,
        )
        mapper.process({"raw_device_state": {"devices": {"keyboard": {"input": None}}}}, 0.1)
        mapper.process(
            {"raw_device_state": {"devices": {"keyboard": {"input": "world"}}}},
            0.2,
        )
        self.assertEqual(backend.events, [("type_text", "hello "), ("type_text", "world ")])

    def test_keyboard_text_action_maps_command_words_to_keys(self) -> None:
        rule = MappingRule(
            source="keyboard.input",
            comparator="present",
            action=MappingAction(type="keyboard_text", text_source="keyboard.input", append_space=True),
        )
        mapper, backend = self.mapper_with([rule])
        mapper.process(
            {"raw_device_state": {"devices": {"keyboard": {"input": "backspace"}}}},
            0.0,
        )
        self.assertEqual(backend.events, [("key_tap", ("ctrl", "backspace"))])

    def test_keyboard_text_action_maps_extended_command_words_to_keys(self) -> None:
        rule = MappingRule(
            source="keyboard.input",
            comparator="present",
            action=MappingAction(type="keyboard_text", text_source="keyboard.input", append_space=True),
        )
        mapper, backend = self.mapper_with([rule])
        expected_events = [
            ("key_tap", ("cmd",)),
            ("key_tap", ("ctrl", "backspace")),
            ("key_tap", ("caps_lock",)),
            ("key_tap", ("space",)),
            ("key_tap", ("0",)),
            ("key_tap", ("1",)),
            ("key_tap", ("2",)),
            ("key_tap", ("3",)),
            ("key_tap", ("4",)),
            ("key_tap", ("5",)),
            ("key_tap", ("6",)),
            ("key_tap", ("7",)),
            ("key_tap", ("8",)),
            ("key_tap", ("9",)),
        ]
        for index, word in enumerate(
            [
                "win",
                "backspace",
                "capslock",
                "space",
                "zero",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
            ]
        ):
            mapper.process({"raw_device_state": {"devices": {"keyboard": {"input": word}}}}, float(index))
            mapper.process({"raw_device_state": {"devices": {"keyboard": {"input": None}}}}, float(index) + 0.01)
        self.assertEqual(backend.events, expected_events)

    def test_keyboard_text_action_normalizes_command_words_before_mapping(self) -> None:
        rule = MappingRule(
            source="keyboard.input",
            comparator="present",
            action=MappingAction(type="keyboard_text", text_source="keyboard.input", append_space=True),
        )
        mapper, backend = self.mapper_with([rule])
        for index, word in enumerate(["Back Space!", "Caps Lock", "Win?", "space bar"]):
            mapper.process({"raw_device_state": {"devices": {"keyboard": {"input": word}}}}, float(index))
            mapper.process({"raw_device_state": {"devices": {"keyboard": {"input": None}}}}, float(index) + 0.01)

        self.assertEqual(
            backend.events,
            [
                ("key_tap", ("ctrl", "backspace")),
                ("key_tap", ("caps_lock",)),
                ("key_tap", ("cmd",)),
                ("key_tap", ("space",)),
            ],
        )

    def test_signal_catalog_exposes_keyboard_prediction_fields(self) -> None:
        signals = SignalCatalog.flatten(
            {
                "raw_device_state": {
                    "devices": {
                        "keyboard": {
                            "input": "hello",
                            "predicted_word": "hello",
                            "prediction_confidence": 0.8,
                            "prediction_sequence": 4,
                            "model_loaded": True,
                        }
                    }
                }
            }
        )
        self.assertEqual(signals["keyboard.input"].value, "hello")
        self.assertEqual(signals["keyboard.prediction_sequence"].value, 4)
        self.assertTrue(signals["keyboard.model_loaded"].value)


class MappingConfigTests(unittest.TestCase):
    def test_default_config_includes_wrist_tab_switching_profile(self) -> None:
        config = default_mapping_config()
        self.assertEqual(
            config.profile_names(),
            [GTA_VICE_CITY_PROFILE_NAME, VIEWER_3D_PROFILE_NAME, TAB_CURSOR_SCROLL_PROFILE_NAME, DEFAULT_PROFILE_NAME],
        )

    def test_wristband_mouse_cursor_profile_uses_calibrated_accel_follow_rule(self) -> None:
        profile = wristband_mouse_cursor_profile()
        self.assertEqual(len(profile.mappings), 1)
        rule = profile.mappings[0]
        self.assertEqual(rule.id, "wrist_mouse_follow_accel")
        self.assertEqual(rule.source, "wristband.sequence")
        self.assertEqual(rule.action.speed_x_source, "wristband.calibrated_accel_x")
        self.assertEqual(rule.action.speed_y_source, "wristband.calibrated_accel_y")
        self.assertGreater(rule.action.move_deadband, 0.0)
        self.assertLess(rule.action.move_smoothing_alpha, 1.0)

    def test_load_config_merges_missing_builtin_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input_mappings.json"
            config = MappingConfig(profiles=[MappingProfile(name="Custom")], active_profile="Custom")
            save_mapping_config(config, path)
            loaded, error = load_mapping_config(path)
            self.assertIsNone(error)
            self.assertIn("Custom", loaded.profile_names())
            self.assertEqual(loaded.profile_names(), ["Custom"])

    def test_load_config_preserves_user_customized_builtin_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input_mappings.json"
            customized = MappingProfile(
                name=TAB_SWITCH_PROFILE_NAME,
                mappings=[
                    MappingRule(
                        id="custom_tab_rule",
                        name="Custom tab rule",
                        source="fused.wrist_rule_value",
                        comparator="eq",
                        threshold="rotate_right_return",
                        action=MappingAction(type="keyboard_tap", keys=["tab"]),
                    )
                ],
            )
            config = MappingConfig(profiles=[customized], active_profile=TAB_SWITCH_PROFILE_NAME)
            save_mapping_config(config, path)

            loaded, error = load_mapping_config(path)

            self.assertIsNone(error)
            loaded_profile = next(profile for profile in loaded.profiles if profile.name == TAB_SWITCH_PROFILE_NAME)
            self.assertEqual([rule.id for rule in loaded_profile.mappings], ["custom_tab_rule"])

    def test_gta_profile_uses_wrist_rules_for_weapon_swaps(self) -> None:
        rules = {rule.id: rule for rule in gta_vice_city_profile().mappings}
        self.assertEqual(rules["gta_follow_cursor_wrist_gyro"].name, "Follow cursor with wrist gyro")
        self.assertEqual(rules["gta_follow_cursor_wrist_gyro"].source, "wrist_cursor.enabled")
        self.assertEqual(rules["gta_follow_cursor_wrist_gyro"].action.type, "mouse_move")
        self.assertEqual(rules["gta_follow_cursor_wrist_gyro"].action.speed_x_source, "wristband.gyro_z")
        self.assertEqual(rules["gta_follow_cursor_wrist_gyro"].action.speed_y_source, "wristband.gyro_x")
        self.assertEqual(rules["gta_swap_weapon_next"].source, "fused.wrist_rule_value")
        self.assertEqual(rules["gta_swap_weapon_next"].threshold, "rotate_right_return")
        self.assertEqual(rules["gta_swap_weapon_previous"].threshold, "rotate_left_return")

    def test_normalize_mapping_config_adds_missing_gta_follow_cursor_rule(self) -> None:
        profile = MappingProfile(
            name=GTA_VICE_CITY_PROFILE_NAME,
            mappings=[
                MappingRule(
                    id="gta_run_forward",
                    name="Run forward",
                    source="hands.right.z_mm",
                    comparator="lt",
                    threshold=430,
                    action=MappingAction(type="keyboard_hold", keys=["w", "space"]),
                )
            ],
        )
        config = MappingConfig(profiles=[profile], active_profile=GTA_VICE_CITY_PROFILE_NAME)

        normalized, changed = normalize_mapping_config(config)

        self.assertTrue(changed)
        self.assertEqual([rule.id for rule in normalized.profiles[0].mappings][:2], ["gta_follow_cursor_wrist_gyro", "gta_run_forward"])
        rules = {rule.id: rule for rule in normalized.profiles[0].mappings}
        self.assertEqual(rules["gta_fire_hold"].action.type, "mouse_hold")
        self.assertEqual(rules["gta_fire_hold"].source, "hands.right.gesture")
        self.assertEqual(rules["gta_fire_hold"].threshold, "gun_gesture")
        for rule_id in ("gta_cheat_police", "gta_cheat_weapons", "gta_cheat_tank", "gta_cheat_health"):
            self.assertEqual(rules[rule_id].action.type, "keyboard_sequence")
            self.assertEqual(rules[rule_id].action.interval_ms, 250)

    def test_runtime_gta_enter_rule_is_not_saved_into_config(self) -> None:
        config = default_mapping_config()
        profile = next(profile for profile in config.profiles if profile.name == GTA_VICE_CITY_PROFILE_NAME)
        self.assertNotIn("gta_enter_peace_runtime", {rule.id for rule in profile.mappings})

        mapper = InputMapper(FakeInputBackend(), config)
        runtime_rule_ids = {rule.id for rule in mapper.active_rules()}

        self.assertIn("gta_enter_peace_runtime", runtime_rule_ids)
        self.assertNotIn("gta_enter_peace_runtime", {rule.id for rule in profile.mappings})

    def test_3d_viewer_profile_has_orbit_pan_pointer_and_zoom(self) -> None:
        profile = viewer_3d_profile()
        rule_ids = {rule.id for rule in profile.mappings}
        self.assertTrue(
            {
                "viewer_orbit_hold",
                "viewer_orbit_follow",
                "viewer_pan_hold",
                "viewer_pan_follow",
                "viewer_pointer_follow",
                "viewer_zoom_in",
                "viewer_zoom_out",
            }.issubset(rule_ids)
        )
        rules = {rule.id: rule for rule in profile.mappings}
        self.assertEqual(rules["viewer_orbit_hold"].conditions, [])
        self.assertEqual(rules["viewer_orbit_follow"].conditions[0].source, "hands.left.gesture")
        self.assertEqual(rules["viewer_pan_follow"].conditions[0].source, "hands.right.gesture")

    def test_wrist_scroll_profile_uses_wrist_rules_for_mouse_scroll(self) -> None:
        rules = {rule.id: rule for rule in wrist_scroll_profile().mappings}
        self.assertEqual(rules["wrist_scroll_up"].source, "fused.wrist_rule_value")
        self.assertEqual(rules["wrist_scroll_up"].threshold, "rotate_right_return")
        self.assertEqual(rules["wrist_scroll_up"].action.type, "mouse_scroll")
        self.assertEqual(rules["wrist_scroll_down"].threshold, "rotate_left_return")
        self.assertEqual(rules["wrist_scroll_down"].action.scroll_y, -1)

    def test_windows_profile_matches_finalized_mapping(self) -> None:
        profile = tabs_cursor_scroll_profile()
        rules = {rule.id: rule for rule in profile.mappings}
        self.assertEqual(len(profile.mappings), 9)
        self.assertEqual(rules["wrist_cursor_follow_gyro"].action.speed_x, -30.0)
        self.assertEqual(rules["wrist_cursor_follow_gyro"].action.speed_y, -30.0)
        self.assertEqual(rules["wrist_tab_cycle_forward"].conditions[0].source, "hands.right.z_mm")
        self.assertEqual(rules["wrist_cursor_left_click"].source, "hands.right.gesture")
        self.assertEqual(rules["wrist_scroll_up"].source, "wristband.gyro_x")
        self.assertEqual(rules["wrist_scroll_up"].action.interval_ms, 90)
        self.assertEqual(rules["wrist_scroll_down"].action.scroll_y, -1)
        self.assertEqual(rules["wrist_cursor_right_click"].source, "hands.left.gesture")
        self.assertEqual(rules["keyboard_type_prediction"].source, "keyboard.input")
        self.assertEqual(rules["keyboard_type_prediction"].action.type, "keyboard_text")
        self.assertTrue(rules["keyboard_type_prediction"].action.append_space)

    def test_normalize_windows_profile_adds_keyboard_typing_mapping(self) -> None:
        profile = MappingProfile(
            name=TAB_CURSOR_SCROLL_PROFILE_NAME,
            mappings=[
                MappingRule(
                    id="wrist_tab_cycle_forward",
                    name="Cycle tabs forward",
                    source="fused.wrist_rule_value",
                    comparator="eq",
                    threshold="rotate_right_return",
                    conditions=[MappingCondition(source="hands.right.z_mm", comparator="lt", threshold="500")],
                    action=MappingAction(type="keyboard_tap", keys=["alt", "tab"]),
                ),
                MappingRule(
                    id="wrist_tab_cycle_backward",
                    name="Cycle tabs backward",
                    source="fused.wrist_rule_value",
                    comparator="eq",
                    threshold="rotate_left_return",
                    conditions=[MappingCondition(source="hands.right.z_mm", comparator="lt", threshold="500")],
                    action=MappingAction(type="keyboard_tap", keys=["alt", "shift", "tab"]),
                ),
                MappingRule(
                    id="wrist_cursor_follow_gyro",
                    name="Follow cursor with wrist gyro",
                    source="wrist_cursor.enabled",
                    comparator="truthy",
                    conditions=[MappingCondition(source="hands.left.gesture", comparator="eq", threshold="open_palm")],
                    action=MappingAction(type="mouse_move"),
                ),
                MappingRule(
                    id="wrist_scroll_up",
                    name="Scroll up",
                    source="wristband.gyro_x",
                    comparator="lt",
                    threshold="-4",
                    action=MappingAction(type="mouse_scroll", interval_ms=90, scroll_y=1),
                ),
                MappingRule(
                    id="wrist_scroll_down",
                    name="Scroll down",
                    source="wristband.gyro_x",
                    comparator="gt",
                    threshold="8",
                    action=MappingAction(type="mouse_scroll", interval_ms=90, scroll_y=-1),
                ),
            ],
        )

        normalized, changed = normalize_mapping_config(MappingConfig(profiles=[profile], active_profile=TAB_CURSOR_SCROLL_PROFILE_NAME))

        self.assertTrue(changed)
        rules = {rule.id: rule for rule in normalized.profiles[0].mappings}
        self.assertIn("keyboard_type_prediction", rules)
        self.assertEqual(rules["keyboard_type_prediction"].source, "keyboard.input")
        self.assertEqual(rules["keyboard_type_prediction"].action.type, "keyboard_text")
        self.assertTrue(rules["keyboard_type_prediction"].action.append_space)

    def test_audio_dock_transcript_command_detects_design_and_windows(self) -> None:
        signals = SignalCatalog.flatten(
            {
                "raw_device_state": {
                    "devices": {
                        "audiodock": {
                            "latest_transcript": "design mode",
                        }
                    }
                }
            }
        )
        self.assertEqual(signals["audiodock.latest_transcript_command"].value, "design mode")
        signals = SignalCatalog.flatten(
            {
                "raw_device_state": {
                    "devices": {
                        "audiodock": {
                            "latest_transcript": "windows please",
                        }
                    }
                }
            }
        )
        self.assertEqual(signals["audiodock.latest_transcript_command"].value, "windows")

    def test_remove_profile_falls_back_and_protects_last_profile(self) -> None:
        config = MappingConfig(profiles=[MappingProfile(), wrist_tab_switching_profile()])
        config.active_profile = TAB_SWITCH_PROFILE_NAME
        self.assertTrue(config.remove_profile(TAB_SWITCH_PROFILE_NAME))
        self.assertEqual(config.active_profile, "Default")
        self.assertFalse(config.remove_profile("Default"))

    def test_wrist_tab_switching_profile_uses_left_fist_and_modifier_combos(self) -> None:
        backend = FakeInputBackend()
        mapper = InputMapper(
            backend,
            MappingConfig(profiles=[wrist_tab_switching_profile()], active_profile=TAB_SWITCH_PROFILE_NAME),
        )
        mapper.enabled = True

        mapper.process(
            hand_snapshot({"wrist_rule_value": "rotate_right_return"}, left_gesture="open_palm"),
            now_s=0.0,
        )
        mapper.process(hand_snapshot({"wrist_rule_value": "none"}, left_gesture="closed_fist"), now_s=0.1)
        mapper.process(
            hand_snapshot({"wrist_rule_value": "rotate_right_return"}, left_gesture="closed_fist"),
            now_s=0.2,
        )
        mapper.process(hand_snapshot({"wrist_rule_value": "none"}, left_gesture="closed_fist"), now_s=0.3)
        mapper.process(
            hand_snapshot({"wrist_rule_value": "rotate_left_return"}, left_gesture="closed_fist"),
            now_s=0.4,
        )

        self.assertEqual(
            backend.events,
            [
                ("key_tap", ("alt", "tab")),
                ("key_tap", ("alt", "shift", "tab")),
            ],
        )

    def test_save_and_load_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input_mappings.json"
            config = MappingConfig()
            config.active().mappings.append(
                MappingRule(
                    source="fused.a",
                    conditions=[MappingCondition(source="fused.b", comparator="truthy", output_keys=["alt"])],
                    action=MappingAction(type="keyboard_tap", keys=["space"]),
                )
            )
            save_mapping_config(config, path)
            loaded, error = load_mapping_config(path)
            self.assertIsNone(error)
            self.assertEqual(loaded.active().mappings[0].source, "fused.a")
            self.assertEqual(loaded.active().mappings[0].conditions[0].source, "fused.b")
            self.assertEqual(loaded.active().mappings[0].conditions[0].output_keys, ["alt"])

    def test_invalid_config_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "input_mappings.json"
            path.write_text(json.dumps({"version": 1, "profiles": [{"mappings": [{"action": {"type": "bad"}}]}]}))
            loaded, error = load_mapping_config(path)
            self.assertIsNotNone(error)
            self.assertEqual(
                loaded.profile_names(),
                [GTA_VICE_CITY_PROFILE_NAME, VIEWER_3D_PROFILE_NAME, TAB_CURSOR_SCROLL_PROFILE_NAME, DEFAULT_PROFILE_NAME],
            )


if __name__ == "__main__":
    unittest.main()
