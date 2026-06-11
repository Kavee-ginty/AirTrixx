from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_bridge import SerialBridge, WRISTBAND_SAMPLE_STALE_S


class SerialBridgeWristbandTests(unittest.TestCase):
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
