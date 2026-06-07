from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


GTA_TRAINING_GESTURES = (
    "run_forward",
    "walk_reverse",
    "turn_right",
    "turn_left",
    "jump",
    "swap_weapon_next",
    "swap_weapon_previous",
)

GTA_TRAINING_DESCRIPTIONS = {
    "run_forward": "Move your right hand forward and hold it briefly.",
    "walk_reverse": "Move your right hand backward and hold it briefly.",
    "turn_right": "Move your left open palm physically right and hold it briefly.",
    "turn_left": "Move your left open palm physically left and hold it briefly.",
    "jump": "Raise your right hand, then return to neutral.",
    "swap_weapon_next": "Rotate the wristband clockwise, then return to neutral.",
    "swap_weapon_previous": "Rotate the wristband counterclockwise, then return to neutral.",
}

_GESTURE_ALIASES = {
    "run_forward": ("run_forward", "walk_forward", "gta_run_forward", "gta_walk_forward"),
    "walk_reverse": ("walk_reverse", "gta_walk_reverse"),
    "turn_right": ("turn_right", "gta_turn_right"),
    "turn_left": ("turn_left", "gta_turn_left"),
    "jump": ("jump", "gta_jump"),
    "swap_weapon_next": ("swap_weapon_next", "gta_swap_weapon_next", "rotate_right"),
    "swap_weapon_previous": ("swap_weapon_previous", "gta_swap_weapon_previous", "rotate_left"),
}

_RULE_BY_GESTURE = {
    "run_forward": "gtavc_right_hand_forward",
    "walk_reverse": "gtavc_right_hand_backward",
    "turn_right": "gtavc_left_palm_turn_right",
    "turn_left": "gtavc_left_palm_turn_left",
    "jump": "gtavc_right_palm_up_jump",
}


class GtaGestureTrainer:
    def __init__(self, gesture_root: Path, model_path: Path) -> None:
        self.gesture_root = Path(gesture_root)
        self.model_path = Path(model_path)

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.model_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) and data.get("version") == 1 else {}

    def train_and_save(self) -> dict[str, Any]:
        model = self.train()
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
        return model

    def train(self) -> dict[str, Any]:
        rule_thresholds: dict[str, dict[str, Any]] = {}
        gesture_counts: dict[str, int] = {}

        metrics: dict[str, tuple[Callable[[dict[str, Any]], float | None], float, float]] = {
            "run_forward": (self._right_depth_excursion, 60.0, 500.0),
            "walk_reverse": (self._right_depth_excursion, 60.0, 500.0),
            "turn_right": (self._left_horizontal_excursion, 0.035, 0.30),
            "turn_left": (self._left_horizontal_excursion, 0.035, 0.30),
            "jump": (self._right_vertical_excursion, 0.04, 0.30),
        }
        for gesture_name, (metric, minimum, maximum) in metrics.items():
            excursions = self._gesture_excursions(gesture_name, metric)
            gesture_counts[gesture_name] = len(excursions)
            signed_threshold = self._trained_signed_threshold(excursions, minimum, maximum)
            if signed_threshold is None:
                continue
            rule_thresholds[_RULE_BY_GESTURE[gesture_name]] = {
                "signed_threshold": signed_threshold,
                "sample_count": len(excursions),
            }

        clockwise = self._gesture_excursions("swap_weapon_next", self._wrist_roll_excursion)
        counterclockwise = self._gesture_excursions("swap_weapon_previous", self._wrist_roll_excursion)
        gesture_counts["swap_weapon_next"] = len(clockwise)
        gesture_counts["swap_weapon_previous"] = len(counterclockwise)
        wrist: dict[str, Any] = {}
        clockwise_threshold = self._trained_wrist_threshold(clockwise)
        counterclockwise_threshold = self._trained_wrist_threshold(counterclockwise)
        if clockwise_threshold is not None:
            wrist["clockwise_sign"] = 1 if clockwise_threshold > 0 else -1
            wrist["clockwise_delta_deg"] = abs(clockwise_threshold)
        if counterclockwise_threshold is not None:
            wrist["counterclockwise_sign"] = 1 if counterclockwise_threshold > 0 else -1
            wrist["counterclockwise_delta_deg"] = abs(counterclockwise_threshold)
        wrist_velocities = self._gesture_velocity_peaks("swap_weapon_next") + self._gesture_velocity_peaks(
            "swap_weapon_previous"
        )
        if wrist_velocities:
            wrist["min_velocity_dps"] = max(3.0, min(12.0, statistics.median(wrist_velocities) * 0.18))

        return {
            "version": 1,
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            "rule_thresholds": rule_thresholds,
            "wrist": wrist,
            "gesture_counts": gesture_counts,
        }

    @staticmethod
    def summary(model: dict[str, Any]) -> str:
        counts = model.get("gesture_counts", {}) if isinstance(model, dict) else {}
        trained = sum(int(counts.get(name, 0)) >= 3 for name in GTA_TRAINING_GESTURES)
        return f"GTA training: {trained}/{len(GTA_TRAINING_GESTURES)} gestures ready (3+ samples each)."

    def _gesture_files(self, gesture_name: str) -> list[Path]:
        primary = sorted((self.gesture_root / gesture_name).glob("*.json"))
        if len(primary) >= 3:
            return primary
        files: list[Path] = []
        for alias in _GESTURE_ALIASES[gesture_name]:
            folder = self.gesture_root / alias
            if folder.is_dir():
                files.extend(folder.glob("*.json"))
        return sorted(set(files))

    def _gesture_excursions(
        self,
        gesture_name: str,
        metric: Callable[[dict[str, Any]], float | None],
    ) -> list[float]:
        excursions: list[float] = []
        for path in self._gesture_files(gesture_name):
            payload = self._load_payload(path)
            value = metric(payload)
            if value is not None and math.isfinite(value):
                excursions.append(value)
        return excursions

    def _gesture_velocity_peaks(self, gesture_name: str) -> list[float]:
        peaks: list[float] = []
        for path in self._gesture_files(gesture_name):
            payload = self._load_payload(path)
            samples = payload.get("samples", []) if isinstance(payload, dict) else []
            timed_rolls: list[tuple[float, float]] = []
            for sample in samples:
                values = sample.get("input_dict", {}) if isinstance(sample, dict) else {}
                roll = self._number(values.get("wrist_roll"))
                sample_s = self._number(sample.get("t_rel")) if isinstance(sample, dict) else None
                if roll is not None and sample_s is not None:
                    timed_rolls.append((sample_s, roll))
            unwrapped = self._unwrap(timed_rolls)
            velocities = [
                abs((current[1] - previous[1]) / (current[0] - previous[0]))
                for previous, current in zip(unwrapped, unwrapped[1:])
                if 0.005 <= current[0] - previous[0] <= 0.25
            ]
            if velocities:
                peaks.append(self._percentile(velocities, 0.90))
        return peaks

    @staticmethod
    def _load_payload(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _series(cls, payload: dict[str, Any], key: str, *, depth: bool = False) -> list[float]:
        series: list[float] = []
        samples = payload.get("samples", []) if isinstance(payload, dict) else []
        for sample in samples:
            values = sample.get("input_dict", {}) if isinstance(sample, dict) else {}
            value = cls._number(values.get(key))
            if value is None or (depth and not 80.0 <= value <= 2500.0):
                continue
            series.append(value)
        return series

    @classmethod
    def _excursion(cls, series: list[float], transform: Callable[[float, float], float]) -> float | None:
        if len(series) < 8:
            return None
        baseline_count = max(3, min(len(series) // 4, 20))
        baseline = statistics.median(series[:baseline_count])
        deltas = [transform(baseline, value) for value in series[baseline_count:]]
        return max(deltas, key=abs) if deltas else None

    @classmethod
    def _right_depth_excursion(cls, payload: dict[str, Any]) -> float | None:
        return cls._excursion(cls._series(payload, "right_hand_z_mm", depth=True), lambda baseline, value: baseline - value)

    @classmethod
    def _left_horizontal_excursion(cls, payload: dict[str, Any]) -> float | None:
        return cls._excursion(cls._series(payload, "left_hand_x"), lambda baseline, value: baseline - value)

    @classmethod
    def _right_vertical_excursion(cls, payload: dict[str, Any]) -> float | None:
        return cls._excursion(cls._series(payload, "right_hand_y"), lambda baseline, value: baseline - value)

    @classmethod
    def _wrist_roll_excursion(cls, payload: dict[str, Any]) -> float | None:
        rolls = cls._series(payload, "wrist_roll")
        if len(rolls) < 8:
            return None
        timed = [(float(index), value) for index, value in enumerate(rolls)]
        unwrapped = [value for _sample_s, value in cls._unwrap(timed)]
        return cls._excursion(unwrapped, lambda baseline, value: value - baseline)

    @staticmethod
    def _trained_signed_threshold(excursions: list[float], minimum: float, maximum: float) -> float | None:
        if len(excursions) < 3:
            return None
        median_excursion = statistics.median(excursions)
        if abs(median_excursion) < minimum:
            return None
        sign = 1.0 if median_excursion > 0 else -1.0
        same_direction = [abs(value) for value in excursions if value * sign > 0]
        if len(same_direction) < max(2, len(excursions) // 2):
            return None
        magnitude = max(minimum, min(maximum, statistics.median(same_direction) * 0.55))
        return sign * magnitude

    @staticmethod
    def _trained_wrist_threshold(excursions: list[float]) -> float | None:
        if len(excursions) < 3:
            return None
        median_excursion = statistics.median(excursions)
        sign = 1.0 if median_excursion > 0 else -1.0
        same_direction = [abs(value) for value in excursions if value * sign > 0]
        if len(same_direction) < max(2, len(excursions) // 2):
            return None
        magnitude = max(4.0, min(8.0, statistics.median(same_direction) * 0.25))
        return sign * magnitude

    @staticmethod
    def _unwrap(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if not samples:
            return []
        result = [samples[0]]
        previous_raw = samples[0][1]
        previous_unwrapped = samples[0][1]
        for sample_s, raw in samples[1:]:
            delta = (raw - previous_raw + 180.0) % 360.0 - 180.0
            previous_unwrapped += delta
            result.append((sample_s, previous_unwrapped))
            previous_raw = raw
        return result

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float:
        ordered = sorted(values)
        index = int(round((len(ordered) - 1) * max(0.0, min(1.0, fraction))))
        return ordered[index]

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
