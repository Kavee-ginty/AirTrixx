from __future__ import annotations

import csv
import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np


IMU_EXPORT_COLUMNS = ("timestamp", "accX", "accY", "accZ", "gyroX", "gyroY", "gyroZ")
IMU_FEATURE_COLUMNS = ("accX", "accY", "accZ", "gyroX", "gyroY", "gyroZ")
DEFAULT_WINDOW_SAMPLES = 60
DEFAULT_MIN_CONFIDENCE = 0.60
DEFAULT_INFERENCE_INTERVAL_S = 0.12
CAPTURE_PHASE_SECONDS = 3.0
EDGE_IMPULSE_SAMPLE_INTERVAL_MS = 20

StatusCallback = Callable[[str], None]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_wristband_imu_sample(
    serial_state: dict[str, Any],
    *,
    timestamp_ms: float | None = None,
    label: str = "",
) -> dict[str, Any] | None:
    devices = serial_state.get("devices", {}) if isinstance(serial_state, dict) else {}
    wrist = devices.get("wristband", {}) if isinstance(devices, dict) else {}
    if not isinstance(wrist, dict):
        return None
    status = str(wrist.get("status", "")).lower()
    if status in {"not_connected", "disconnected", "tbd"}:
        return None
    accel = wrist.get("accel", {})
    gyro = wrist.get("gyro", {})
    if not isinstance(accel, dict) or not isinstance(gyro, dict):
        return None
    values = {
        "accX": _number(accel.get("x")),
        "accY": _number(accel.get("y")),
        "accZ": _number(accel.get("z")),
        "gyroX": _number(gyro.get("x")),
        "gyroY": _number(gyro.get("y")),
        "gyroZ": _number(gyro.get("z")),
    }
    if any(value is None for value in values.values()):
        return None
    timestamp = timestamp_ms if timestamp_ms is not None else time.time() * 1000.0
    return {
        "timestamp": round(float(timestamp), 3),
        **{key: float(value) for key, value in values.items() if value is not None},
    }


def wristband_sequence(serial_state: dict[str, Any]) -> Any:
    devices = serial_state.get("devices", {}) if isinstance(serial_state, dict) else {}
    wrist = devices.get("wristband", {}) if isinstance(devices, dict) else {}
    if not isinstance(wrist, dict):
        return None
    return wrist.get("sequence")


def sanitize_label(label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in label.strip())
    return cleaned.strip("_") or "gesture"


def edge_impulse_sample_filename(label: str, timestamp: str, index: int) -> str:
    return f"{sanitize_label(label)}.{timestamp}.{max(1, int(index)):03d}.csv"


def infer_label_from_sample_filename(path: Path) -> str:
    name = Path(path).name
    if "." in name:
        label = name.split(".", 1)[0]
        if label:
            return label
    stem = Path(path).stem
    parts = stem.split("_")
    if len(parts) >= 4 and parts[0].isdigit() and parts[1].isdigit() and parts[-2] == "sample":
        return "_".join(parts[2:-2])
    if len(parts) >= 3 and parts[-2] == "sample":
        return "_".join(parts[:-2])
    return stem


def load_labels(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            candidates = data.get("labels") or data.get("classes") or data.get("categories")
            if isinstance(candidates, list):
                return [str(item).strip() for item in candidates if str(item).strip()]
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
        return []
    labels: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "," in line:
            labels.extend(part.strip() for part in line.split(",") if part.strip())
        else:
            labels.append(line)
    return labels


def write_labels(path: Path, labels: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(labels).strip() + "\n", encoding="utf-8")


def find_companion_labels(model_path: Path) -> Path | None:
    candidates = [
        model_path.with_suffix(".labels.txt"),
        model_path.with_suffix(".txt"),
        model_path.parent / "labels.txt",
        model_path.parent / "labels.json",
        model_path.parent / "metadata.json",
        model_path.parent / "model_metadata.json",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


@dataclass
class _InputSpec:
    shape: list[Any]
    layout: str
    window_samples: int
    feature_count: int


class WristbandModelRuntime:
    def __init__(
        self,
        model_path: Path,
        labels_path: Path,
        *,
        on_log: StatusCallback | None = None,
        default_window_samples: int = DEFAULT_WINDOW_SAMPLES,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        inference_interval_s: float = DEFAULT_INFERENCE_INTERVAL_S,
    ) -> None:
        self.model_path = Path(model_path)
        self.labels_path = Path(labels_path)
        self.on_log = on_log
        self.default_window_samples = max(1, int(default_window_samples))
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.inference_interval_s = max(0.02, float(inference_interval_s))
        self.labels: list[str] = []
        self.model_error = ""
        self.model_value = "none"
        self.model_loaded = False
        self._interpreter: Any = None
        self._runtime_name = ""
        self._input_index = 0
        self._input_dtype: Any = np.float32
        self._input_quantization: tuple[float, float] = (0.0, 0.0)
        self._output_details: list[dict[str, Any]] = []
        self._input_spec = _InputSpec([], "flat", self.default_window_samples, self.default_window_samples * 6)
        self._buffer: list[list[float]] = []
        self._last_inference_s = 0.0
        self._last_sequence: Any = None
        self._has_last_sequence = False
        self.reload()

    @property
    def status(self) -> str:
        if self.model_loaded:
            label_text = f"{len(self.labels)} label(s)" if self.labels else "labels missing"
            runtime_text = self._runtime_name or "TFLite"
            return f"Loaded TFLite model via {runtime_text}, {label_text}"
        if self.model_error:
            return self.model_error
        return "No wristband model loaded"

    @property
    def required_samples(self) -> int:
        return self._input_spec.window_samples

    def reload(self) -> bool:
        self.model_loaded = False
        self.model_error = ""
        self.model_value = "none"
        self._interpreter = None
        self._runtime_name = ""
        self._input_index = 0
        self._input_dtype = np.float32
        self._input_quantization = (0.0, 0.0)
        self._output_details = []
        self._buffer.clear()
        self._last_sequence = None
        self._has_last_sequence = False
        self.labels = load_labels(self.labels_path)
        if not self.model_path.exists():
            self.model_error = f"Missing model: {self.model_path}"
            return False
        try:
            Interpreter, runtime_name = self._load_tflite_interpreter()
        except Exception as exc:
            self.model_error = f"TFLite runtime unavailable: {exc}"
            self._log(self.model_error)
            return False
        try:
            self._interpreter = Interpreter(model_path=str(self.model_path))
            self._interpreter.allocate_tensors()
            self._runtime_name = runtime_name
            input_detail = self._interpreter.get_input_details()[0]
            output_details = list(self._interpreter.get_output_details())
            self._input_index = int(input_detail["index"])
            self._input_dtype = input_detail.get("dtype", np.float32)
            self._input_quantization = self._quantization_tuple(input_detail)
            self._output_details = output_details
            shape = input_detail.get("shape_signature")
            if shape is None or not len(shape):
                shape = input_detail.get("shape", [])
            self._input_spec = self._infer_input_spec(list(shape))
        except Exception as exc:
            self.model_error = f"Could not load wristband model: {exc}"
            self._log(self.model_error)
            self._interpreter = None
            return False
        self.model_loaded = True
        self._log(f"Loaded wristband model: {self.model_path}")
        return True

    @staticmethod
    def _load_tflite_interpreter() -> tuple[Any, str]:
        errors: list[str] = []
        try:
            from ai_edge_litert.interpreter import Interpreter

            return Interpreter, "LiteRT"
        except Exception as exc:
            errors.append(f"ai-edge-litert: {exc}")
        try:
            from tflite_runtime.interpreter import Interpreter

            return Interpreter, "tflite-runtime"
        except Exception as exc:
            errors.append(f"tflite-runtime: {exc}")
        try:
            import tensorflow as tf

            return tf.lite.Interpreter, "TensorFlow Lite"
        except Exception as exc:
            errors.append(f"tensorflow: {exc}")
        raise RuntimeError("; ".join(errors))

    def classify_serial_state(self, serial_state: dict[str, Any], now_s: float | None = None) -> str:
        sample = extract_wristband_imu_sample(serial_state)
        if sample is None:
            self._buffer.clear()
            self._last_sequence = None
            self._has_last_sequence = False
            self.model_value = "none"
            return self.model_value
        sequence = wristband_sequence(serial_state)
        if sequence is not None:
            if self._has_last_sequence and sequence == self._last_sequence:
                return self.model_value
            self._last_sequence = sequence
            self._has_last_sequence = True
        return self.classify_sample(sample, now_s=now_s)

    def classify_sample(self, sample: dict[str, Any], now_s: float | None = None) -> str:
        now_s = time.monotonic() if now_s is None else now_s
        features = [float(sample[key]) for key in IMU_FEATURE_COLUMNS]
        self._buffer.append(features)
        del self._buffer[: max(0, len(self._buffer) - self.required_samples)]
        if not self.model_loaded or self._interpreter is None:
            self.model_value = "none"
            return self.model_value
        if len(self._buffer) < self.required_samples:
            self.model_value = "none"
            return self.model_value
        if now_s - self._last_inference_s < self.inference_interval_s:
            return self.model_value
        self._last_inference_s = now_s
        try:
            input_tensor = self._format_input_tensor()
            self._interpreter.set_tensor(self._input_index, input_tensor)
            self._interpreter.invoke()
            outputs = [
                self._dequantize_output(self._interpreter.get_tensor(detail["index"]), detail)
                for detail in self._output_details
            ]
            label, confidence = self._decode_outputs(outputs)
        except Exception as exc:
            self.model_error = f"Wristband inference failed: {exc}"
            self.model_value = "none"
            self._log(self.model_error)
            return self.model_value
        self.model_value = label if confidence >= self.min_confidence else "none"
        return self.model_value

    def _infer_input_spec(self, shape: list[Any]) -> _InputSpec:
        dims = []
        for dim in shape:
            try:
                number = int(dim)
            except (TypeError, ValueError):
                number = 0
            dims.append(number if number > 0 else None)
        without_batch = dims[1:] if len(dims) >= 2 and (dims[0] in (None, 1)) else dims
        layout = "flat"
        window_samples = self.default_window_samples
        feature_count = self.default_window_samples * len(IMU_FEATURE_COLUMNS)
        if len(without_batch) == 1:
            fixed = without_batch[0]
            if fixed:
                feature_count = fixed
                window_samples = max(1, feature_count // len(IMU_FEATURE_COLUMNS))
        elif len(without_batch) >= 3 and without_batch[2] in (None, 1):
            first, second = without_batch[0], without_batch[1]
            if second == len(IMU_FEATURE_COLUMNS):
                layout = "time_features_channel"
                window_samples = first or self.default_window_samples
                feature_count = window_samples * len(IMU_FEATURE_COLUMNS)
            elif first == len(IMU_FEATURE_COLUMNS):
                layout = "features_time_channel"
                window_samples = second or self.default_window_samples
                feature_count = window_samples * len(IMU_FEATURE_COLUMNS)
        elif len(without_batch) >= 2:
            first, second = without_batch[0], without_batch[1]
            if second == len(IMU_FEATURE_COLUMNS):
                layout = "time_features"
                window_samples = first or self.default_window_samples
                feature_count = window_samples * len(IMU_FEATURE_COLUMNS)
            elif first == len(IMU_FEATURE_COLUMNS):
                layout = "features_time"
                window_samples = second or self.default_window_samples
                feature_count = window_samples * len(IMU_FEATURE_COLUMNS)
            elif first and second:
                layout = "time_features"
                window_samples = first
                feature_count = first * second
        return _InputSpec(shape=shape, layout=layout, window_samples=max(1, int(window_samples)), feature_count=max(1, int(feature_count)))

    def _format_input_tensor(self) -> np.ndarray:
        window = np.asarray(self._buffer[-self.required_samples :], dtype=np.float32)
        spec = self._input_spec
        if spec.layout == "time_features":
            tensor = window.reshape(1, spec.window_samples, len(IMU_FEATURE_COLUMNS))
        elif spec.layout == "time_features_channel":
            tensor = window.reshape(1, spec.window_samples, len(IMU_FEATURE_COLUMNS), 1)
        elif spec.layout == "features_time":
            tensor = window.T.reshape(1, len(IMU_FEATURE_COLUMNS), spec.window_samples)
        elif spec.layout == "features_time_channel":
            tensor = window.T.reshape(1, len(IMU_FEATURE_COLUMNS), spec.window_samples, 1)
        else:
            flat = window.reshape(-1)
            if flat.size < spec.feature_count:
                flat = np.pad(flat, (spec.feature_count - flat.size, 0), mode="constant")
            elif flat.size > spec.feature_count:
                flat = flat[-spec.feature_count :]
            dims = []
            for dim in spec.shape:
                try:
                    number = int(dim)
                except (TypeError, ValueError):
                    number = 0
                dims.append(number if number > 0 else None)
            tensor = flat.astype(np.float32) if len(dims) == 1 else flat.reshape(1, -1).astype(np.float32)
        return self._cast_input_tensor(tensor)

    def _cast_input_tensor(self, tensor: np.ndarray) -> np.ndarray:
        dtype = np.dtype(self._input_dtype)
        if np.issubdtype(dtype, np.floating):
            return tensor.astype(dtype)
        scale, zero_point = self._input_quantization
        if not scale:
            return tensor.astype(dtype)
        quantized = np.round(tensor / scale + zero_point)
        if np.issubdtype(dtype, np.integer):
            info = np.iinfo(dtype)
            quantized = np.clip(quantized, info.min, info.max)
        return quantized.astype(dtype)

    @staticmethod
    def _quantization_tuple(detail: dict[str, Any]) -> tuple[float, float]:
        quantization = detail.get("quantization")
        if isinstance(quantization, tuple) and len(quantization) == 2:
            try:
                return float(quantization[0]), float(quantization[1])
            except (TypeError, ValueError):
                return 0.0, 0.0
        params = detail.get("quantization_parameters")
        if isinstance(params, dict):
            scales = params.get("scales")
            zero_points = params.get("zero_points")
            try:
                if scales is not None and len(scales):
                    scale = float(scales[0])
                    zero_point = float(zero_points[0]) if zero_points is not None and len(zero_points) else 0.0
                    return scale, zero_point
            except (TypeError, ValueError):
                return 0.0, 0.0
        return 0.0, 0.0

    def _dequantize_output(self, output: Any, detail: dict[str, Any]) -> Any:
        array = np.asarray(output)
        if array.dtype.kind not in {"i", "u"}:
            return output
        scale, zero_point = self._quantization_tuple(detail)
        if not scale:
            return output
        return (array.astype(np.float32) - zero_point) * scale

    def _decode_outputs(self, outputs: list[Any]) -> tuple[str, float]:
        for output in outputs:
            if isinstance(output, np.ndarray) and output.dtype.kind in {"U", "S", "O"} and output.size:
                return str(output.reshape(-1)[0]), 1.0
        probabilities: Any = None
        for output in outputs:
            if isinstance(output, list) and output and isinstance(output[0], dict):
                probabilities = output[0]
                break
            if isinstance(output, dict):
                probabilities = output
                break
        if isinstance(probabilities, dict) and probabilities:
            label, score = max(probabilities.items(), key=lambda item: float(item[1]))
            return str(label), float(score)
        array = np.asarray(outputs[0])
        if array.size == 0:
            return "none", 0.0
        scores = array.reshape(-1).astype(float)
        index = int(np.argmax(scores))
        label = self.labels[index] if index < len(self.labels) else f"class_{index}"
        return label, float(scores[index])

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)


@dataclass
class WristbandCsvCapture:
    output_dir: Path
    on_status: StatusCallback | None = None
    is_recording: bool = False
    label: str = ""
    started_s: float = 0.0
    samples: list[dict[str, Any]] = field(default_factory=list)
    completed_samples: list[list[dict[str, Any]]] = field(default_factory=list)
    phase: str = "idle"
    phase_started_s: float = 0.0
    phase_seconds: float = CAPTURE_PHASE_SECONDS
    _last_sequence: Any = None
    _has_last_sequence: bool = False

    @property
    def sample_count(self) -> int:
        count = len(self.completed_samples)
        if self.samples:
            count += 1
        return count

    @property
    def row_count(self) -> int:
        return len(self.samples) + sum(len(segment) for segment in self.completed_samples)

    @property
    def is_record_phase(self) -> bool:
        return self.is_recording and self.phase == "record"

    def start(self, label: str) -> bool:
        if self.is_recording:
            self._status("Wristband capture is already running.")
            return False
        self.label = sanitize_label(label)
        self.samples = []
        self.completed_samples = []
        self._last_sequence = None
        self._has_last_sequence = False
        self.started_s = time.time()
        self.phase = "record"
        self.phase_started_s = time.monotonic()
        self.is_recording = True
        self._status(f"Recording wristband label: {self.label}. Green phase records, red phase pauses.")
        return True

    def update_phase(self, now_s: float | None = None) -> None:
        if not self.is_recording:
            self.phase = "idle"
            return
        now_s = time.monotonic() if now_s is None else now_s
        phase_seconds = max(0.1, float(self.phase_seconds))
        while now_s - self.phase_started_s >= phase_seconds:
            self.phase_started_s += phase_seconds
            if self.phase == "record":
                self._finish_current_sample()
                self.phase = "rest"
            else:
                self.samples = []
                self.phase = "record"
            self._last_sequence = None
            self._has_last_sequence = False

    def phase_remaining_s(self, now_s: float | None = None) -> float:
        if not self.is_recording:
            return 0.0
        now_s = time.monotonic() if now_s is None else now_s
        self.update_phase(now_s)
        return max(0.0, max(0.1, float(self.phase_seconds)) - (now_s - self.phase_started_s))

    def phase_fraction_remaining(self, now_s: float | None = None) -> float:
        if not self.is_recording:
            return 0.0
        remaining = self.phase_remaining_s(now_s)
        return max(0.0, min(1.0, remaining / max(0.1, float(self.phase_seconds))))

    def _finish_current_sample(self) -> None:
        if self.samples:
            self.completed_samples.append(list(self.samples))
        self.samples = []

    def add_serial_state(self, serial_state: dict[str, Any]) -> None:
        if not self.is_recording:
            return
        self.update_phase()
        if self.phase != "record":
            return
        sample = extract_wristband_imu_sample(serial_state, label=self.label)
        if sample is not None:
            self.samples.append(sample)

    def stop(self) -> list[Path]:
        if not self.is_recording:
            return []
        self.update_phase()
        if self.phase == "record":
            self._finish_current_sample()
        self.is_recording = False
        self.phase = "idle"
        self._last_sequence = None
        self._has_last_sequence = False
        if not self.completed_samples:
            self._status("Wristband capture stopped with no valid IMU samples.")
            return []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        paths: list[Path] = []
        for index, segment in enumerate(self.completed_samples, start=1):
            path = self.output_dir / edge_impulse_sample_filename(self.label, timestamp, index)
            write_samples_csv(path, segment)
            paths.append(path)
        self.completed_samples = []
        self.samples = []
        self._status(f"Saved {len(paths)} wristband sample file(s).")
        return paths

    def _status(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)


def write_samples_csv(
    path: Path,
    samples: list[dict[str, Any]],
    *,
    sample_interval_ms: int = EDGE_IMPULSE_SAMPLE_INTERVAL_MS,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=IMU_EXPORT_COLUMNS)
        writer.writeheader()
        for index, sample in enumerate(samples):
            row = {key: sample.get(key, "") for key in IMU_EXPORT_COLUMNS}
            row["timestamp"] = index * int(sample_interval_ms)
            writer.writerow(row)


def export_combined_csv(source_dir: Path, output_path: Path) -> int:
    files = sorted(Path(source_dir).glob("*.csv"))
    count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=IMU_EXPORT_COLUMNS)
        writer.writeheader()
        for path in files:
            with path.open("r", newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source)
                for row in reader:
                    writer.writerow({key: row.get(key, "") for key in IMU_EXPORT_COLUMNS})
                    count += 1
    return count


def install_model_files(source_model: Path, target_model: Path, source_labels: Path | None, target_labels: Path) -> list[str]:
    target_model.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_model, target_model)
    labels: list[str] = []
    if source_labels is not None and source_labels.exists():
        labels = load_labels(source_labels)
    if labels:
        write_labels(target_labels, labels)
    elif target_labels.exists():
        target_labels.unlink()
    return labels
