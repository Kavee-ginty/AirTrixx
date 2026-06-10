from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wristband_model import (
    EDGE_IMPULSE_SAMPLE_INTERVAL_MS,
    IMU_EXPORT_COLUMNS,
    WristbandCsvCapture,
    WristbandModelRuntime,
    edge_impulse_sample_filename,
    extract_wristband_imu_sample,
    export_combined_csv,
    infer_label_from_sample_filename,
    sanitize_label,
    write_samples_csv,
)


def serial_state(sequence: int | None = None) -> dict[str, object]:
    wrist: dict[str, object] = {
        "status": "connected",
        "accel": {"x": 1, "y": 2, "z": 3},
        "gyro": {"x": 4, "y": 5, "z": 6},
    }
    if sequence is not None:
        wrist["sequence"] = sequence
    return {
        "devices": {
            "wristband": wrist
        }
    }


class WristbandModelTests(unittest.TestCase):
    def test_extract_sample_uses_requested_training_columns(self) -> None:
        sample = extract_wristband_imu_sample(serial_state(), timestamp_ms=123.456, label="flick")

        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual(tuple(sample.keys()), IMU_EXPORT_COLUMNS)
        self.assertEqual(sample["timestamp"], 123.456)
        self.assertEqual(sample["accX"], 1.0)
        self.assertEqual(sample["gyroZ"], 6.0)
        self.assertNotIn("label", sample)

    def test_capture_writes_exact_csv_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = WristbandCsvCapture(Path(tmpdir))
            self.assertTrue(capture.start("rotate right"))
            capture.add_serial_state(serial_state())
            paths = capture.stop()

            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].name.startswith("rotate_right."))
            self.assertEqual(infer_label_from_sample_filename(paths[0]), "rotate_right")
            with paths[0].open("r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                self.assertEqual(tuple(next(reader)), IMU_EXPORT_COLUMNS)

    def test_export_combined_csv_keeps_exact_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_samples_csv(
                root / "a.csv",
                [extract_wristband_imu_sample(serial_state(), timestamp_ms=1, label="rotate_left")],
            )
            output = root / "combined.csv"

            count = export_combined_csv(root, output)

            self.assertEqual(count, 1)
            with output.open("r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                self.assertEqual(tuple(next(reader)), IMU_EXPORT_COLUMNS)

    def test_capture_keeps_repeated_sequence_rows_during_green_phase(self) -> None:
        capture = WristbandCsvCapture(Path("unused"))
        self.assertTrue(capture.start("flick"))
        capture.add_serial_state(serial_state(sequence=10))
        capture.add_serial_state(serial_state(sequence=10))
        capture.add_serial_state(serial_state(sequence=11))

        self.assertEqual(len(capture.samples), 3)

    def test_capture_records_only_green_phases_as_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = WristbandCsvCapture(Path(tmpdir))
            capture.phase_seconds = 3.0
            self.assertTrue(capture.start("flick"))
            start_s = capture.phase_started_s
            capture.add_serial_state(serial_state(sequence=1))
            capture.update_phase(start_s + 3.1)
            self.assertEqual(capture.phase, "rest")
            capture.add_serial_state(serial_state(sequence=2))
            self.assertEqual(capture.sample_count, 1)
            self.assertEqual(capture.row_count, 1)
            capture.update_phase(start_s + 6.1)
            self.assertEqual(capture.phase, "record")
            capture.add_serial_state(serial_state(sequence=3))
            paths = capture.stop()

            self.assertEqual(len(paths), 2)

    def test_sanitize_label_preserves_mapper_friendly_name(self) -> None:
        self.assertEqual(sanitize_label("wrist circle!"), "wrist_circle")

    def test_edge_impulse_filename_starts_with_label(self) -> None:
        filename = edge_impulse_sample_filename("rotate left", "20260611_120000", 7)

        self.assertEqual(filename, "rotate_left.20260611_120000.007.csv")
        self.assertEqual(infer_label_from_sample_filename(Path(filename)), "rotate_left")

    def test_write_samples_csv_uses_constant_relative_20ms_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "idle.001.csv"
            write_samples_csv(
                path,
                [
                    extract_wristband_imu_sample(serial_state(), timestamp_ms=1000),
                    extract_wristband_imu_sample(serial_state(), timestamp_ms=1047),
                    extract_wristband_imu_sample(serial_state(), timestamp_ms=1090),
                ],
            )

            with path.open("r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual([int(row["timestamp"]) for row in rows], [0, EDGE_IMPULSE_SAMPLE_INTERVAL_MS, 40])
        self.assertNotIn("label", rows[0])

    def test_tflite_channelized_input_shape_formats_window(self) -> None:
        runtime = WristbandModelRuntime.__new__(WristbandModelRuntime)
        runtime.default_window_samples = 150
        runtime._input_spec = runtime._infer_input_spec([1, 150, 6, 1])
        runtime._buffer = [[float(axis) for axis in range(6)] for _ in range(150)]
        runtime._input_dtype = np.float32
        runtime._input_quantization = (0.0, 0.0)

        tensor = runtime._format_input_tensor()

        self.assertEqual(tensor.shape, (1, 150, 6, 1))
        self.assertEqual(tensor.dtype, np.float32)

    def test_quantized_tflite_input_casts_with_scale_and_zero_point(self) -> None:
        runtime = WristbandModelRuntime.__new__(WristbandModelRuntime)
        runtime.default_window_samples = 1
        runtime._input_spec = runtime._infer_input_spec([1, 6])
        runtime._buffer = [[0.0, 0.5, 1.0, -0.5, -1.0, 2.0]]
        runtime._input_dtype = np.int8
        runtime._input_quantization = (0.5, 0.0)

        tensor = runtime._format_input_tensor()

        self.assertEqual(tensor.dtype, np.int8)
        self.assertEqual(tensor.tolist(), [[0, 1, 2, -1, -2, 4]])


if __name__ == "__main__":
    unittest.main()
