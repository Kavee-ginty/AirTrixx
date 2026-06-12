from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_paths import build_app_paths, user_data_root
from audio_dock import AudioDockBridge
from config import DEFAULT_CALIBRATION, load_calibration_with_warnings, save_calibration
from gui import AirTrixxGUI


class FakeConnectedSerialBridge:
    is_connected = True

    def __init__(self) -> None:
        self.commands: list[dict] = []

    def send_command(self, command: dict) -> bool:
        self.commands.append(command)
        return True


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
