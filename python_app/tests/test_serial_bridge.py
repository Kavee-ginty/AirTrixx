from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_bridge import DEVICE_DELTA_STALE_S, SerialBridge, WRISTBAND_SAMPLE_STALE_S


class SerialBridgeWristbandTests(unittest.TestCase):
    def test_generic_delta_recursively_merges_and_preserves_slow_fields(self) -> None:
        bridge = SerialBridge()
        with bridge._latest_lock:
            bridge._store_state_locked(
                {
                    "devices": {
                        "camdock": {
                            "status": "ok",
                            "sequence": 10,
                            "battery_level": 75,
                            "tof": {"left_mm": 500, "right_mm": 600},
                        }
                    }
                }
            )
            bridge._store_state_locked(
                {
                    "device_delta": {
                        "device": "camdock",
                        "sequence": 11,
                        "t_ms": 100,
                        "fields": {"status": "ok", "tof": {"left_mm": 450}},
                    }
                }
            )

        camdock = bridge.get_latest_state()["devices"]["camdock"]
        self.assertEqual(camdock["battery_level"], 75)
        self.assertEqual(camdock["tof"], {"left_mm": 450, "right_mm": 600})

    def test_out_of_order_delta_is_ignored_and_aggregate_does_not_regress_newer_delta(self) -> None:
        bridge = SerialBridge()
        with bridge._latest_lock:
            bridge._store_state_locked(
                {
                    "devices": {
                        "fans": {"status": "ok", "sequence": 10, "battery_level": 80, "input": "off"}
                    }
                }
            )
            bridge._store_state_locked(
                {
                    "device_delta": {
                        "device": "fans",
                        "sequence": 12,
                        "t_ms": 120,
                        "fields": {"input": "on", "fan_on": True},
                    }
                }
            )
            bridge._store_state_locked(
                {
                    "device_delta": {
                        "device": "fans",
                        "sequence": 11,
                        "t_ms": 110,
                        "fields": {"input": "off", "fan_on": False},
                    }
                }
            )
            bridge._store_state_locked(
                {
                    "devices": {
                        "fans": {"status": "ok", "sequence": 10, "battery_level": 81, "input": "off"}
                    }
                }
            )

        fans = bridge.get_latest_state()["devices"]["fans"]
        self.assertEqual(fans["sequence"], 12)
        self.assertEqual(fans["battery_level"], 81)
        self.assertEqual(fans["input"], "on")
        self.assertTrue(fans["fan_on"])

    def test_delta_freshness_marks_device_disconnected_but_preserves_battery(self) -> None:
        bridge = SerialBridge()
        bridge._latest_state = {
            "devices": {
                "camdock": {
                    "status": "ok",
                    "sequence": 10,
                    "battery_level": 75,
                    "tof": {"left_mm": 100, "right_mm": 200},
                }
            }
        }
        bridge._device_last_received_s["camdock"] = time.monotonic() - DEVICE_DELTA_STALE_S - 0.1
        bridge._device_sequences["camdock"] = 10

        camdock = bridge.get_latest_state()["devices"]["camdock"]
        self.assertEqual(camdock["status"], "not_connected")
        self.assertEqual(camdock["battery_level"], 75)
        self.assertEqual(camdock["tof"], {"left_mm": None, "right_mm": None})

    def test_compact_keyboard_sample_merges_without_losing_slow_fields(self) -> None:
        bridge = SerialBridge()
        with bridge._latest_lock:
            bridge._store_state_locked(
                {
                    "sequence": 5,
                    "devices": {
                        "keyboard": {
                            "status": "ok",
                            "sequence": 10,
                            "battery_level": 75,
                            "tof": {"sensor_1_mm": 100},
                        }
                    },
                }
            )
            bridge._store_state_locked(
                {
                    "keyboard_sample": {
                        "status": "ok",
                        "sequence": 11,
                        "tof": {"sensor_1_mm": 90},
                    }
                }
            )

        keyboard = bridge.get_latest_state()["devices"]["keyboard"]
        self.assertEqual(keyboard["sequence"], 11)
        self.assertEqual(keyboard["battery_level"], 75)
        self.assertEqual(keyboard["tof"], {"sensor_1_mm": 90})

    def test_disconnected_full_state_clears_queued_wristband_samples(self) -> None:
        bridge = SerialBridge()
        with bridge._latest_lock:
            bridge._store_state_locked(
                {
                    "devices": {
                        "wristband": {
                            "status": "ok",
                            "sequence": 10,
                            "accel": {"x": 1, "y": 2, "z": 3},
                            "gyro": {"x": 4, "y": 5, "z": 6},
                        }
                    }
                }
            )
            bridge._store_state_locked(
                {
                    "wristband_sample": {
                        "status": "ok",
                        "sequence": 11,
                        "accel": {"x": 1, "y": 2, "z": 3},
                        "gyro": {"x": 4, "y": 5, "z": 6},
                    }
                }
            )
            bridge._store_state_locked(
                {
                    "devices": {
                        "wristband": {
                            "status": "not_connected",
                            "accel": {"x": None, "y": None, "z": None},
                            "gyro": {"x": None, "y": None, "z": None},
                        }
                    }
                }
            )

        self.assertEqual(bridge.drain_wristband_states(), [])
        self.assertEqual(bridge.get_latest_state()["devices"]["wristband"]["status"], "not_connected")

    def test_stale_wristband_sample_is_marked_disconnected_and_motion_is_cleared(self) -> None:
        bridge = SerialBridge()
        bridge._latest_state = {
            "devices": {
                "wristband": {
                    "status": "ok",
                    "sequence": 10,
                    "t_ms": 200,
                    "battery_level": 75,
                    "accel": {"x": 1, "y": 2, "z": 3},
                    "gyro": {"x": 4, "y": 5, "z": 6},
                    "pitch": 7,
                    "roll": 8,
                    "yaw": 9,
                }
            }
        }
        bridge._wristband_states.append(bridge._latest_state)
        bridge._wristband_last_sample_s = time.monotonic() - WRISTBAND_SAMPLE_STALE_S - 0.1

        state = bridge.get_latest_state()
        wristband = state["devices"]["wristband"]

        self.assertEqual(wristband["status"], "not_connected")
        self.assertEqual(wristband["battery_level"], 75)
        self.assertEqual(wristband["accel"], {"x": None, "y": None, "z": None})
        self.assertEqual(wristband["gyro"], {"x": None, "y": None, "z": None})
        self.assertEqual(bridge.drain_wristband_states(), [])


if __name__ == "__main__":
    unittest.main()
