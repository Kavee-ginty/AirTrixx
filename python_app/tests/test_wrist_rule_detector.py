from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wrist_rule_detector import WristReturnRuleDetector


class WristReturnRuleDetectorTests(unittest.TestCase):
    @staticmethod
    def feed(detector: WristReturnRuleDetector, values: list[tuple[float, float, float]]) -> list[str]:
        events: list[str] = []
        for index, (gx, gy, gz) in enumerate(values):
            event = detector.process(index * 0.02, gx, gy, gz, now_s=index * 0.02)
            if event:
                events.append(event)
        return events

    def test_detects_right_return_from_positive_then_negative_y_peaks(self) -> None:
        detector = WristReturnRuleDetector()
        values = [(0, 0, 0)] * 10 + [(10, 230, 8)] * 15 + [(0, 0, 0)] * 3 + [(8, -220, 10)] * 15 + [(0, 0, 0)] * 12

        self.assertEqual(self.feed(detector, values), ["rotate_right_return"])

    def test_detects_left_return_from_negative_then_positive_y_peaks(self) -> None:
        detector = WristReturnRuleDetector()
        values = [(0, 0, 0)] * 10 + [(10, -230, 8)] * 15 + [(0, 0, 0)] * 3 + [(8, 220, 10)] * 15 + [(0, 0, 0)] * 12

        self.assertEqual(self.feed(detector, values), ["rotate_left_return"])

    def test_rejects_large_general_movements_below_first_peak_threshold(self) -> None:
        detector = WristReturnRuleDetector()
        values = [(80, 120, -100), (-90, -130, 105), (70, 110, -95)] * 20

        self.assertEqual(self.feed(detector, values), [])

    def test_rejects_peak_when_other_axis_is_too_large(self) -> None:
        detector = WristReturnRuleDetector()
        values = [(150, 230, 10)] * 15 + [(10, -230, 10)] * 15 + [(0, 0, 0)] * 12

        self.assertEqual(self.feed(detector, values), [])

    def test_detection_is_exposed_as_a_short_mapper_pulse(self) -> None:
        detector = WristReturnRuleDetector()
        values = [(0, 0, 0)] * 10 + [(10, 230, 8)] * 15 + [(0, 0, 0)] * 3 + [(8, -220, 10)] * 15 + [(0, 0, 0)] * 12
        self.feed(detector, values)

        event_time = detector.last_event_time_s
        assert event_time is not None
        self.assertEqual(detector.output(event_time)["value"], "rotate_right_return")
        self.assertEqual(detector.output(event_time + detector.config.pulse_s + 0.01)["value"], "none")


if __name__ == "__main__":
    unittest.main()
