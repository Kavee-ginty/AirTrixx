from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_paths import build_app_paths, user_data_root
from audio_dock import AudioDockBridge
from config import DEFAULT_CALIBRATION, _normalize_runtime_calibration, load_calibration_with_warnings, save_calibration
from gui import AirTrixxGUI
from input_mapper import GTA_VICE_CITY_PROFILE_NAME


class FakeConnectedSerialBridge:
    is_connected = True

    def __init__(self) -> None:
        self.commands: list[dict] = []

    def send_command(self, command: dict) -> bool:
        self.commands.append(command)
        return True


class FakeVar:
    def __init__(self, value=None) -> None:
        self.value = value

    def set(self, value) -> None:
        self.value = value

    def get(self):
        return self.value


class FakeMapper:
    def __init__(self, active_profile: str = "Default", enabled: bool = False) -> None:
        self.enabled = enabled
        self.config = SimpleNamespace(active_profile=active_profile)
        self.enabled_calls: list[bool] = []
        self.active_profile_calls: list[str] = []

    def set_active_profile(self, profile_name: str) -> bool:
        self.active_profile_calls.append(profile_name)
        self.config.active_profile = profile_name
        return True

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.enabled_calls.append(self.enabled)


class ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None) -> None:
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class AppPathTests(unittest.TestCase):
    def test_windows_user_data_uses_appdata(self) -> None:
        with patch("app_paths.platform.system", return_value="Windows"), patch.dict(
            os.environ,
            {"APPDATA": r"C:\Users\tester\AppData\Roaming"},
            clear=True,
        ):
            self.assertEqual(user_data_root(), Path(r"C:\Users\tester\AppData\Roaming") / "AirTrixx")

    def test_macos_user_data_uses_application_support(self) -> None:
        with patch("app_paths.platform.system", return_value="Darwin"), patch("app_paths.Path.home", return_value=Path("/Users/tester")):
            self.assertEqual(user_data_root(), Path("/Users/tester/Library/Application Support/AirTrixx"))

    def test_build_paths_keeps_runtime_files_under_user_data(self) -> None:
        with patch("app_paths.platform.system", return_value="Darwin"), patch("app_paths.Path.home", return_value=Path("/Users/tester")):
            paths = build_app_paths()
        self.assertEqual(paths.calibration_path, paths.config_dir / "calibration.json")
        self.assertEqual(paths.mapping_path, paths.config_dir / "input_mappings.json")
        self.assertEqual(paths.servo_debug_log_path, paths.logs_dir / "servo_debug.log")
        self.assertEqual(paths.audio_recording_path, paths.temp_dir / "last_esp32_recording.wav")
        self.assertEqual(paths.gesture_data_dir, paths.user_data_dir / "gestures")
        self.assertEqual(paths.keyboard_data_dir, paths.user_data_dir / "keyboard")
        self.assertEqual(paths.wristband_data_dir, paths.user_data_dir / "wristband")
        self.assertEqual(paths.wristband_model_dir, paths.wristband_data_dir / "model")
        self.assertEqual(paths.audio_training_dir, paths.user_data_dir / "audio_training")
        self.assertEqual(paths.keyboard_dataset_path, paths.keyboard_data_dir / "raw_samples.csv")
        self.assertEqual(paths.keyboard_model_path, paths.keyboard_data_dir / "word_knn_model.npz")
        self.assertEqual(paths.keyboard_words_path, paths.keyboard_data_dir / "current_training_words.txt")
        self.assertEqual(paths.wristband_model_path, paths.wristband_model_dir / "wristband_gesture_model.tflite")
        self.assertEqual(paths.wristband_labels_path, paths.wristband_model_dir / "labels.txt")


class ConfigTests(unittest.TestCase):
    def test_corrupt_calibration_falls_back_and_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "calibration.json"
            path.write_text("{", encoding="utf-8")
            calibration, warnings = load_calibration_with_warnings(path)
            backups = list(Path(tmpdir).glob("calibration.invalid_*.json"))
        self.assertEqual(calibration["cam_pan_center"], DEFAULT_CALIBRATION["cam_pan_center"])
        self.assertTrue(warnings)
        self.assertEqual(len(backups), 1)

    def test_save_calibration_filters_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "calibration.json"
            save_calibration({"cam_pan_center": 123, "unknown": "drop"}, path)
            text = path.read_text(encoding="utf-8")
        self.assertIn('"cam_pan_center": 123', text)
        self.assertNotIn("unknown", text)

    def test_runtime_calibration_migrates_old_heavy_camera_defaults(self) -> None:
        calibration = dict(DEFAULT_CALIBRATION)
        calibration.update(
            {
                "camera_width": 1280,
                "camera_height": 720,
                "tracking_frame_skip": 1,
                "preview_fps": 10,
            }
        )

        normalized = _normalize_runtime_calibration(calibration)

        self.assertEqual(normalized["camera_width"], 424)
        self.assertEqual(normalized["camera_height"], 240)
        self.assertEqual(normalized["tracking_frame_skip"], 0)
        self.assertEqual(normalized["preview_fps"], 6)


class AudioDockSettingsTests(unittest.TestCase):
    def test_audio_dock_prefers_saved_deepgram_key(self) -> None:
        bridge = AudioDockBridge(deepgram_api_key=" saved-key ")
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "env-key"}):
            self.assertEqual(bridge.load_deepgram_key(), "saved-key")

    def test_audio_dock_uses_env_key_as_fallback(self) -> None:
        bridge = AudioDockBridge()
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "env-key"}):
            self.assertEqual(bridge.load_deepgram_key(), "env-key")

    def test_audio_dock_connects_without_deepgram_key(self) -> None:
        logs: list[str] = []
        bridge = AudioDockBridge(serial_bridge=FakeConnectedSerialBridge(), on_log=logs.append)

        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(bridge.connect())

        self.assertTrue(bridge.is_connected)
        self.assertEqual(bridge.status, "Waiting for Clap")
        self.assertTrue(any("transcription needs a key" in message for message in logs))

    def test_audio_dock_saves_labeled_training_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            samples: list[tuple[str, Path]] = []
            bridge = AudioDockBridge(training_data_dir=Path(tmpdir))
            bridge.on_training_sample = lambda label, path: samples.append((label, path))
            bridge.last_audio_data = b"RIFFfakewav"
            bridge.last_trigger = "Double clap"

            saved = bridge.save_last_training_sample("false trigger")

            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.parent, Path(tmpdir) / "false_trigger")
            self.assertEqual(saved.read_bytes(), b"RIFFfakewav")
            self.assertEqual(samples, [("false_trigger", saved)])

    def test_audio_dock_sends_training_record_control(self) -> None:
        serial_bridge = FakeConnectedSerialBridge()
        bridge = AudioDockBridge(serial_bridge=serial_bridge)
        bridge.is_connected = True

        self.assertTrue(bridge.send_control("training_record"))

        self.assertEqual(serial_bridge.commands, [{"cmd": "audiodock", "control": "training_record"}])

    def test_audio_dock_sends_training_record_count(self) -> None:
        serial_bridge = FakeConnectedSerialBridge()
        bridge = AudioDockBridge(serial_bridge=serial_bridge)
        bridge.is_connected = True

        self.assertTrue(bridge.send_control("training_record", count=10))

        self.assertEqual(serial_bridge.commands, [{"cmd": "audiodock", "control": "training_record", "count": 10}])

    def test_audio_dock_sends_voice_mode_control(self) -> None:
        serial_bridge = FakeConnectedSerialBridge()
        bridge = AudioDockBridge(serial_bridge=serial_bridge)
        bridge.is_connected = True

        self.assertTrue(bridge.send_control("vice_city"))

        self.assertEqual(serial_bridge.commands, [{"cmd": "audiodock", "control": "mode_voice"}])

    def test_audio_dock_indexed_chunks_assemble_in_order(self) -> None:
        serial_bridge = FakeConnectedSerialBridge()
        transcripts: list[tuple[str, str]] = []
        bridge = AudioDockBridge(serial_bridge=serial_bridge, on_transcript=lambda trigger, text: transcripts.append((trigger, text)))
        bridge.connect()

        with patch("audio_dock.threading.Thread", ImmediateThread), patch("audio_dock.time.sleep", lambda _: None), patch.object(
            bridge, "_transcribe", return_value="hello world"
        ):
            bridge.handle_antenna_line("AUDIODOCK_TRIGGER:1,8")
            bridge.handle_antenna_line("AUDIODOCK_AUDIO_CHUNK:0,4,52494646")
            bridge.handle_antenna_line("AUDIODOCK_AUDIO_CHUNK:1,4,64617461")

        self.assertEqual(bridge.last_audio_data, b"RIFFdata")
        self.assertEqual(bridge.latest_transcript, "hello world")
        self.assertEqual(transcripts[-1], ("Single clap", "hello world"))

    def test_audio_dock_indexed_chunks_assemble_out_of_order(self) -> None:
        serial_bridge = FakeConnectedSerialBridge()
        bridge = AudioDockBridge(serial_bridge=serial_bridge)
        bridge.connect()

        with patch("audio_dock.threading.Thread", ImmediateThread), patch("audio_dock.time.sleep", lambda _: None), patch.object(
            bridge, "_transcribe", return_value="ordered"
        ):
            bridge.handle_antenna_line("AUDIODOCK_TRIGGER:2,8")
            bridge.handle_antenna_line("AUDIODOCK_AUDIO_CHUNK:1,4,64617461")
            bridge.handle_antenna_line("AUDIODOCK_AUDIO_CHUNK:0,4,52494646")

        self.assertEqual(bridge.last_audio_data, b"RIFFdata")
        self.assertEqual(bridge.latest_transcript, "ordered")

    def test_gta_profile_activation_arms_mapper_for_voice_cheats(self) -> None:
        logs: list[str] = []
        calls: list[object] = []
        gui = SimpleNamespace(
            input_mapper=FakeMapper(enabled=False),
            mapping_profile_var=FakeVar("Default"),
            mapping_enabled_var=FakeVar(False),
            _schedule_mapping_views_refresh=lambda: calls.append("refresh"),
            _update_mapping_status=lambda: calls.append("status"),
            _refresh_mapping_profile_combo=lambda: calls.append("combo"),
            _clear_audio_dock_voice_gate=lambda: calls.append("clear"),
            _sync_audio_dock_listening_mode=lambda profile_name=None, now_s=None: calls.append((profile_name, now_s)),
            log=logs.append,
        )

        result = AirTrixxGUI._activate_profile_with_audio_sync(
            gui,
            GTA_VICE_CITY_PROFILE_NAME,
            reason="Audio Dock transcript",
        )

        self.assertTrue(result)
        self.assertTrue(gui.input_mapper.enabled)
        self.assertEqual(gui.mapping_enabled_var.value, True)
        self.assertEqual(gui.mapping_profile_var.value, GTA_VICE_CITY_PROFILE_NAME)
        self.assertIn("GTA Vice City profile enabled the input mapper for voice cheats.", logs)
        self.assertTrue(any(call[0] == GTA_VICE_CITY_PROFILE_NAME for call in calls if isinstance(call, tuple)))
        self.assertNotIn("clear", calls)

    def test_audio_dock_legacy_chunk_parsing_still_works(self) -> None:
        serial_bridge = FakeConnectedSerialBridge()
        bridge = AudioDockBridge(serial_bridge=serial_bridge)
        bridge.connect()
        expected_audio = b"RIFF" + (b"A" * 20) + b"data" + (b"B" * 20)

        with patch("audio_dock.threading.Thread", ImmediateThread), patch("audio_dock.time.sleep", lambda _: None), patch.object(
            bridge, "_transcribe", return_value="legacy"
        ):
            bridge.handle_antenna_line(f"AUDIODOCK_TRIGGER:1,{len(expected_audio)}")
            bridge.handle_antenna_line(f"AUDIODOCK_AUDIO:{(b'RIFF' + (b'A' * 20)).hex()}")
            bridge.handle_antenna_line(f"AUDIODOCK_AUDIO:{(b'data' + (b'B' * 20)).hex()}")

        self.assertEqual(bridge.last_audio_data, expected_audio)
        self.assertEqual(bridge.latest_transcript, "legacy")

    def test_audio_dock_new_trigger_clears_old_transcript(self) -> None:
        serial_bridge = FakeConnectedSerialBridge()
        transcripts: list[tuple[str, str]] = []
        bridge = AudioDockBridge(serial_bridge=serial_bridge, on_transcript=lambda trigger, text: transcripts.append((trigger, text)))
        bridge.connect()
        bridge.latest_transcript = "old text"
        bridge.last_trigger = "Double clap"

        bridge.handle_antenna_line("AUDIODOCK_TRIGGER:1,8")

        self.assertEqual(bridge.latest_transcript, "")
        self.assertEqual(bridge.last_trigger, "Single clap")
        self.assertEqual(transcripts[-1], ("Single clap", ""))

    def test_audio_dock_voice_trigger_label(self) -> None:
        self.assertEqual(AudioDockBridge._trigger_label_for_type(3), "Voice command")

    def test_audio_dock_thumb_up_arms_voice_gate(self) -> None:
        gui = AirTrixxGUI.__new__(AirTrixxGUI)
        gui.input_mapper = SimpleNamespace(config=SimpleNamespace(active_profile="GTA Vice City"))
        gui._audio_dock_voice_gate_until_s = 0.0
        gui._audio_dock_thumb_up_seen = {"left": False, "right": False}
        gui._audio_dock_last_listening_control = ""
        gui.audio_dock_bridge = SimpleNamespace(is_connected=False)
        gui.log = lambda *_args, **_kwargs: None
        gui._clear_audio_dock_voice_gate = AirTrixxGUI._clear_audio_dock_voice_gate.__get__(gui, AirTrixxGUI)
        gui._sync_audio_dock_listening_mode = lambda *args, **kwargs: None

        gui._update_audio_dock_voice_gate({"right": {"visible": True, "gesture": "thumb_up"}}, 10.0)

        self.assertTrue(gui._audio_dock_voice_gate_active(10.1))
        self.assertEqual(gui._audio_dock_voice_gate_until_s, 22.0)

    def test_audio_dock_transcript_requests_game_mode(self) -> None:
        self.assertTrue(AirTrixxGUI._audio_dock_transcript_requests_game_mode("please switch to game mode"))
        self.assertTrue(AirTrixxGUI._audio_dock_transcript_requests_game_mode("game mode"))
        self.assertFalse(AirTrixxGUI._audio_dock_transcript_requests_game_mode("game over"))

    def test_voice_command_transcript_reopens_gta_voice_gate(self) -> None:
        gui = AirTrixxGUI.__new__(AirTrixxGUI)
        gui.audio_dock_last_trigger_var = FakeVar("-")
        gui.audio_dock_latest_transcript_var = FakeVar("-")
        gui.input_mapper = SimpleNamespace(config=SimpleNamespace(active_profile=GTA_VICE_CITY_PROFILE_NAME))
        gui._audio_dock_voice_gate_until_s = 0.0
        gui.log = lambda *_args, **_kwargs: None
        gui._activate_profile_with_audio_sync = lambda *_args, **_kwargs: True
        gui._schedule_text_update = lambda: None

        with patch("gui.time.monotonic", return_value=100.0):
            gui._set_audio_dock_transcript("Voice command", "health")

        self.assertEqual(gui._audio_dock_voice_gate_until_s, 112.0)

    def test_audio_dock_gta_profile_stays_in_voice_mode(self) -> None:
        gui = AirTrixxGUI.__new__(AirTrixxGUI)
        gui.input_mapper = SimpleNamespace(config=SimpleNamespace(active_profile="GTA Vice City"))
        gui._audio_dock_voice_gate_active = lambda *args, **kwargs: False

        self.assertEqual(gui._desired_audio_dock_listening_control("GTA Vice City"), "mode_voice")
        self.assertEqual(gui._desired_audio_dock_listening_control("Default"), "mode_clap")

    def test_audio_dock_stale_transcript_result_is_ignored(self) -> None:
        serial_bridge = FakeConnectedSerialBridge()
        transcripts: list[tuple[str, str]] = []
        bridge = AudioDockBridge(serial_bridge=serial_bridge, on_transcript=lambda trigger, text: transcripts.append((trigger, text)))
        bridge.connect()

        first_capture = bridge._start_capture("Single clap", 8)
        assert first_capture is not None
        second_capture = bridge._start_capture("Double clap", 8)
        assert second_capture is not None

        with patch("audio_dock.time.sleep", lambda _: None):
            bridge._transcribe_and_send(first_capture.capture_id, first_capture.trigger_label, b"first", skip_transcription=True)

        self.assertEqual(bridge.latest_transcript, "")
        self.assertEqual(transcripts[-1], ("Double clap", ""))
        self.assertEqual(serial_bridge.commands, [])

    def test_dashboard_offline_status_uses_red_styling(self) -> None:
        label, bg, fg, color = AirTrixxGUI._battery_status_style(None, "not_connected")
        self.assertEqual(label, "Offline")
        self.assertEqual(bg, "#fef3f2")
        self.assertEqual(fg, "#b42318")
        self.assertEqual(color, "#ef4444")


if __name__ == "__main__":
    unittest.main()
