from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from input_backend import PynputInputBackend


class _StubMouseController:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []

    def move(self, dx: int, dy: int) -> None:
        self.moves.append((dx, dy))


class _StubUser32:
    def __init__(self, result: int = 1) -> None:
        self.result = result
        self.calls: list[tuple[int, int]] = []
        self.map_calls: list[int] = []

    def SendInput(self, count, pointer, size) -> int:
        self.calls.append((int(count), int(size)))
        return self.result

    def MapVirtualKeyW(self, code: int, map_type: int) -> int:
        self.map_calls.append(int(code))
        return int(code)


class InputBackendTests(unittest.TestCase):
    def test_move_uses_sendinput_when_available(self) -> None:
        backend = PynputInputBackend.__new__(PynputInputBackend)
        backend._mouse_controller = _StubMouseController()
        backend._sendinput_mouse_enabled = True
        backend._user32 = _StubUser32()

        backend.move(12, -7)

        self.assertEqual(backend._mouse_controller.moves, [])
        self.assertEqual(len(backend._user32.calls), 1)

    def test_move_falls_back_to_mouse_controller_when_sendinput_unavailable(self) -> None:
        backend = PynputInputBackend.__new__(PynputInputBackend)
        backend._mouse_controller = _StubMouseController()
        backend._sendinput_mouse_enabled = False
        backend._user32 = None

        backend.move(8, -3)

        self.assertEqual(backend._mouse_controller.moves, [(8, -3)])

    def test_tap_keys_uses_sendinput_for_enter_on_windows(self) -> None:
        backend = PynputInputBackend.__new__(PynputInputBackend)
        backend._keyboard_controller = SimpleNamespace()
        backend._sendinput_keyboard_enabled = True
        backend._user32 = _StubUser32()

        backend.tap_keys(["enter"])

        self.assertEqual(len(backend._user32.calls), 2)
        self.assertEqual(backend._user32.map_calls, [0x0D])

    def test_fake_backend_records_hold_duration_for_taps(self) -> None:
        from input_backend import FakeInputBackend

        backend = FakeInputBackend()
        backend.tap_keys(["enter"], hold_ms=250)

        self.assertEqual(backend.events, [("key_tap", ("enter",), 250)])


if __name__ == "__main__":
    unittest.main()
