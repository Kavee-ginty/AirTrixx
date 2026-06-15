from __future__ import annotations

import ctypes
import platform
import time
from dataclasses import dataclass
from typing import Any, Protocol


class InputBackend(Protocol):
    @property
    def available(self) -> bool:
        ...

    @property
    def error(self) -> str | None:
        ...

    def press_key(self, token: str) -> None:
        ...

    def release_key(self, token: str) -> None:
        ...

    def tap_keys(self, tokens: list[str], hold_ms: int = 0) -> None:
        ...

    def type_text(self, text: str) -> None:
        ...

    def press_mouse(self, button: str) -> None:
        ...

    def release_mouse(self, button: str) -> None:
        ...

    def click_mouse(self, button: str, clicks: int = 1) -> None:
        ...

    def scroll(self, dx: int = 0, dy: int = 0) -> None:
        ...

    def move(self, dx: int = 0, dy: int = 0) -> None:
        ...

    def move_absolute(self, x: int, y: int) -> None:
        ...


KEY_ALIASES: dict[str, str] = {
    "control": "ctrl",
    "ctrl_l": "ctrl_l",
    "ctrl_r": "ctrl_r",
    "command": "cmd",
    "win": "cmd",
    "windows": "cmd",
    "super": "cmd",
    "option": "alt",
    "escape": "esc",
    "return": "enter",
    "delete": "delete",
    "del": "delete",
    "pgup": "page_up",
    "pageup": "page_up",
    "pgdn": "page_down",
    "pagedown": "page_down",
    "up_arrow": "up",
    "down_arrow": "down",
    "left_arrow": "left",
    "right_arrow": "right",
    "plus": "+",
    "minus": "-",
    "plus_sign": "+",
    "minus_sign": "-",
}


BUTTON_ALIASES: dict[str, str] = {
    "primary": "left",
    "secondary": "right",
    "wheel": "middle",
    "mid": "middle",
}


def normalize_key_token(token: str) -> str:
    cleaned = " ".join(str(token).strip().split())
    if not cleaned:
        return ""
    lowered = cleaned.replace(" ", "_").replace("-", "_").lower()
    return KEY_ALIASES.get(lowered, lowered)


def normalize_mouse_button(button: str) -> str:
    cleaned = str(button).strip().lower().replace(" ", "_").replace("-", "_")
    return BUTTON_ALIASES.get(cleaned, cleaned or "left")


def parse_key_combo(value: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw_tokens = [str(item) for item in value]
    else:
        text = str(value).replace("+", ",")
        raw_tokens = text.split(",")
    tokens = [normalize_key_token(item) for item in raw_tokens]
    return [token for token in tokens if token]


@dataclass
class _PynputModules:
    keyboard: Any
    mouse: Any


if platform.system() == "Windows":
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]

    _INPUT_KEYBOARD = 1
    _INPUT_MOUSE = 0
    _KEYEVENTF_EXTENDEDKEY = 0x0001
    _KEYEVENTF_KEYUP = 0x0002
    _KEYEVENTF_SCANCODE = 0x0008
    _MOUSEEVENTF_MOVE = 0x0001
else:
    _INPUT = None
    _INPUT_KEYBOARD = 0
    _INPUT_MOUSE = 0
    _KEYEVENTF_EXTENDEDKEY = 0
    _KEYEVENTF_KEYUP = 0
    _KEYEVENTF_SCANCODE = 0
    _MOUSEEVENTF_MOVE = 0


WINDOWS_VK_CODES: dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "caps_lock": 0x14,
    "esc": 0x1B,
    "space": 0x20,
    "page_up": 0x21,
    "page_down": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "cmd": 0x5B,
    "cmd_l": 0x5B,
    "cmd_r": 0x5C,
    "+": 0xBB,
    "-": 0xBD,
}

WINDOWS_EXTENDED_KEYS = {
    "right",
    "up",
    "left",
    "down",
    "insert",
    "delete",
    "home",
    "end",
    "page_up",
    "page_down",
    "cmd",
    "cmd_l",
    "cmd_r",
    "alt_r",
    "ctrl_r",
}


class PynputInputBackend:
    def __init__(self) -> None:
        self._available = False
        self._error: str | None = None
        self._modules: _PynputModules | None = None
        self._keyboard_controller: Any = None
        self._mouse_controller: Any = None
        self._user32: Any = None
        self._sendinput_keyboard_enabled = False
        self._sendinput_mouse_enabled = False
        try:
            from pynput import keyboard, mouse

            self._modules = _PynputModules(keyboard=keyboard, mouse=mouse)
            self._keyboard_controller = keyboard.Controller()
            self._mouse_controller = mouse.Controller()
            if platform.system() == "Windows":
                user32 = getattr(getattr(ctypes, "windll", None), "user32", None)
                if user32 is not None and _INPUT is not None:
                    self._user32 = user32
                    self._sendinput_keyboard_enabled = True
                    self._sendinput_mouse_enabled = True
            self._available = True
        except Exception as exc:  # pragma: no cover - depends on OS permissions/display
            self._error = f"pynput input backend unavailable: {exc}"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    def press_key(self, token: str) -> None:
        normalized = normalize_key_token(token)
        key_spec = self._windows_key_spec(normalized)
        if self._send_keyboard_spec(key_spec, key_up=False):
            return
        key = self._resolve_key(normalized)
        if key is not None:
            self._keyboard_controller.press(key)

    def release_key(self, token: str) -> None:
        normalized = normalize_key_token(token)
        key_spec = self._windows_key_spec(normalized)
        if self._send_keyboard_spec(key_spec, key_up=True):
            return
        key = self._resolve_key(normalized)
        if key is not None:
            self._keyboard_controller.release(key)

    def tap_keys(self, tokens: list[str], hold_ms: int = 0) -> None:
        normalized = [normalize_key_token(token) for token in tokens if normalize_key_token(token)]
        if len(normalized) == 1 and normalized[0] == "+":
            if self._sendinput_keyboard_enabled and self._user32 is not None and _INPUT is not None:
                plus_spec = self._windows_key_spec("=")
                shift_spec = self._windows_key_spec("shift")
                if plus_spec is not None and shift_spec is not None:
                    self._send_keyboard_spec(shift_spec, key_up=False)
                    self._send_keyboard_spec(plus_spec, key_up=False)
                    if hold_ms > 0:
                        ctypes.windll.kernel32.Sleep(int(hold_ms))
                    self._send_keyboard_spec(plus_spec, key_up=True)
                    self._send_keyboard_spec(shift_spec, key_up=True)
                    return
        key_specs = [self._windows_key_spec(token) for token in normalized]
        if normalized and all(spec is not None for spec in key_specs):
            for spec in key_specs:
                self._send_keyboard_spec(spec, key_up=False)
            if hold_ms > 0:
                ctypes.windll.kernel32.Sleep(int(hold_ms))
            for spec in reversed(key_specs):
                self._send_keyboard_spec(spec, key_up=True)
            return
        keys = [self._resolve_key(token) for token in normalized]
        keys = [key for key in keys if key is not None]
        for key in keys:
            self._keyboard_controller.press(key)
        if hold_ms > 0:
            time.sleep(max(0.0, hold_ms / 1000.0))
        for key in reversed(keys):
            self._keyboard_controller.release(key)

    def type_text(self, text: str) -> None:
        self._keyboard_controller.type(str(text))

    def press_mouse(self, button: str) -> None:
        resolved = self._resolve_button(button)
        if resolved is not None:
            self._mouse_controller.press(resolved)

    def release_mouse(self, button: str) -> None:
        resolved = self._resolve_button(button)
        if resolved is not None:
            self._mouse_controller.release(resolved)

    def click_mouse(self, button: str, clicks: int = 1) -> None:
        resolved = self._resolve_button(button)
        if resolved is not None:
            self._mouse_controller.click(resolved, max(1, int(clicks)))

    def scroll(self, dx: int = 0, dy: int = 0) -> None:
        self._mouse_controller.scroll(int(dx), int(dy))

    def move(self, dx: int = 0, dy: int = 0) -> None:
        dx = int(dx)
        dy = int(dy)
        if not self._send_relative_mouse_input(dx, dy):
            self._mouse_controller.move(dx, dy)

    def move_absolute(self, x: int, y: int) -> None:
        self._mouse_controller.position = (int(x), int(y))

    def _send_relative_mouse_input(self, dx: int, dy: int) -> bool:
        if not self._sendinput_mouse_enabled or self._user32 is None or _INPUT is None:
            return False
        if dx == 0 and dy == 0:
            return True
        mouse_input = _INPUT(
            type=_INPUT_MOUSE,
            mi=_MOUSEINPUT(
                dx=int(dx),
                dy=int(dy),
                mouseData=0,
                dwFlags=_MOUSEEVENTF_MOVE,
                time=0,
                dwExtraInfo=0,
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(mouse_input), ctypes.sizeof(_INPUT))
        return int(sent) == 1

    def _send_keyboard_input(self, token: str, *, key_up: bool) -> bool:
        key_spec = self._windows_key_spec(token)
        return self._send_keyboard_spec(key_spec, key_up=key_up)

    def _send_keyboard_spec(self, key_spec: tuple[int, bool] | None, *, key_up: bool) -> bool:
        if not self._sendinput_keyboard_enabled or self._user32 is None or _INPUT is None:
            return False
        if key_spec is None:
            return False
        scan_code, extended = key_spec
        flags = _KEYEVENTF_SCANCODE
        if extended:
            flags |= _KEYEVENTF_EXTENDEDKEY
        if key_up:
            flags |= _KEYEVENTF_KEYUP
        keyboard_input = _INPUT(
            type=_INPUT_KEYBOARD,
            ki=_KEYBDINPUT(
                wVk=0,
                wScan=scan_code,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(keyboard_input), ctypes.sizeof(_INPUT))
        return int(sent) == 1

    def _windows_key_spec(self, token: str) -> tuple[int, bool] | None:
        if platform.system() != "Windows" or self._user32 is None:
            return None
        normalized = normalize_key_token(token)
        if not normalized:
            return None
        if normalized == "+":
            vk_code = 0xBB
        elif normalized == "-":
            vk_code = 0xBD
        elif normalized == "=":
            vk_code = 0xBB
        elif len(normalized) == 1:
            vk_code = ord(normalized.upper())
        elif normalized.startswith("f") and normalized[1:].isdigit():
            index = int(normalized[1:])
            if 1 <= index <= 24:
                vk_code = 0x6F + index
            else:
                return None
        else:
            vk_code = WINDOWS_VK_CODES.get(normalized)
        if vk_code is None:
            return None
        scan_code = int(self._user32.MapVirtualKeyW(int(vk_code), 0))
        if scan_code == 0:
            return None
        extended = normalized in WINDOWS_EXTENDED_KEYS
        if normalized == "=":
            extended = False
        return scan_code, extended

    def _resolve_key(self, token: str) -> Any:
        if not self._modules:
            return None
        token = normalize_key_token(token)
        if not token:
            return None
        keyboard = self._modules.keyboard
        if len(token) == 1:
            return keyboard.KeyCode.from_char(token)
        if token.startswith("f") and token[1:].isdigit():
            key = getattr(keyboard.Key, token, None)
            if key is not None:
                return key
        named_key = getattr(keyboard.Key, token, None)
        if named_key is not None:
            return named_key
        try:
            return keyboard.KeyCode.from_char(token)
        except Exception:
            return None

    def _resolve_button(self, button: str) -> Any:
        if not self._modules:
            return None
        name = normalize_mouse_button(button)
        return getattr(self._modules.mouse.Button, name, None)


class FakeInputBackend:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []
        self._available = True
        self._error: str | None = None

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    def press_key(self, token: str) -> None:
        self.events.append(("key_down", normalize_key_token(token)))

    def release_key(self, token: str) -> None:
        self.events.append(("key_up", normalize_key_token(token)))

    def tap_keys(self, tokens: list[str], hold_ms: int = 0) -> None:
        normalized = [normalize_key_token(token) for token in tokens if normalize_key_token(token)]
        if hold_ms > 0:
            self.events.append(("key_tap", tuple(normalized), int(hold_ms)))
        else:
            self.events.append(("key_tap", tuple(normalized)))

    def type_text(self, text: str) -> None:
        self.events.append(("type_text", str(text)))

    def press_mouse(self, button: str) -> None:
        self.events.append(("mouse_down", normalize_mouse_button(button)))

    def release_mouse(self, button: str) -> None:
        self.events.append(("mouse_up", normalize_mouse_button(button)))

    def click_mouse(self, button: str, clicks: int = 1) -> None:
        self.events.append(("mouse_click", normalize_mouse_button(button), max(1, int(clicks))))

    def scroll(self, dx: int = 0, dy: int = 0) -> None:
        self.events.append(("scroll", int(dx), int(dy)))

    def move(self, dx: int = 0, dy: int = 0) -> None:
        self.events.append(("move", int(dx), int(dy)))

    def move_absolute(self, x: int, y: int) -> None:
        self.events.append(("move_absolute", int(x), int(y)))
