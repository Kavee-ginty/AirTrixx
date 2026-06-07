from __future__ import annotations

import os
import sys
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

    def tap_keys(self, tokens: list[str]) -> None:
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

    def begin_pointer_session(
        self,
        session_id: str,
        *,
        foreground_process: str = "",
        center_in_foreground: bool = False,
        hide_cursor: bool = False,
        restore_cursor: bool = False,
        pointer_mode: str = "",
        activate_foreground: bool = True,
    ) -> bool:
        ...

    def pointer_session_active(self, session_id: str) -> bool:
        ...

    def move_pointer_session(self, session_id: str, dx: int = 0, dy: int = 0) -> bool:
        ...

    def end_pointer_session(self, session_id: str) -> None:
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


class PynputInputBackend:
    def __init__(self) -> None:
        self._available = False
        self._error: str | None = None
        self._modules: _PynputModules | None = None
        self._keyboard_controller: Any = None
        self._mouse_controller: Any = None
        self._pointer_sessions: dict[str, dict[str, Any]] = {}
        self._touch_injection_ready = False
        self._touch_user32: Any = None
        self._touch_info_type: Any = None
        try:
            from pynput import keyboard, mouse

            self._modules = _PynputModules(keyboard=keyboard, mouse=mouse)
            self._keyboard_controller = keyboard.Controller()
            self._mouse_controller = mouse.Controller()
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
        key = self._resolve_key(token)
        if key is not None:
            self._keyboard_controller.press(key)

    def release_key(self, token: str) -> None:
        key = self._resolve_key(token)
        if key is not None:
            self._keyboard_controller.release(key)

    def tap_keys(self, tokens: list[str]) -> None:
        keys = [self._resolve_key(token) for token in tokens]
        keys = [key for key in keys if key is not None]
        for key in keys:
            self._keyboard_controller.press(key)
        for key in reversed(keys):
            self._keyboard_controller.release(key)

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
        self._mouse_controller.move(int(dx), int(dy))

    def move_absolute(self, x: int, y: int) -> None:
        self._mouse_controller.position = (int(x), int(y))

    def begin_pointer_session(
        self,
        session_id: str,
        *,
        foreground_process: str = "",
        center_in_foreground: bool = False,
        hide_cursor: bool = False,
        restore_cursor: bool = False,
        pointer_mode: str = "",
        activate_foreground: bool = True,
    ) -> bool:
        if session_id in self._pointer_sessions:
            return self.pointer_session_active(session_id)
        target = str(foreground_process).strip().lower()
        target_window = self._target_process_window(foreground_process) if target else self._foreground_window()
        if not target_window:
            return False
        matched_process = self._window_process_name(target_window) if target else ""
        if target and activate_foreground:
            self._activate_window(target_window)
        elif target and not self._foreground_process_matches(target):
            return False
        mode = str(pointer_mode).strip().lower()
        if mode == "touch":
            center = self._window_client_center(target_window)
            bounds = self._window_client_bounds(target_window)
            if center is None or bounds is None or not self._initialize_touch_injection():
                return False
            self._pointer_sessions[session_id] = {
                "foreground_process": matched_process or target,
                "target_window": target_window,
                "pointer_mode": "touch",
                "touch_active": False,
                "touch_point": center,
                "touch_bounds": bounds,
            }
            return True
        original_position = tuple(self._mouse_controller.position)
        hidden = bool(hide_cursor and self._set_cursor_visible(False))
        if center_in_foreground:
            center = self._window_client_center(target_window)
            if center is None:
                if hidden:
                    self._set_cursor_visible(True)
                return False
            self.move_absolute(*center)
        self._pointer_sessions[session_id] = {
            "foreground_process": matched_process or target,
            "target_window": target_window,
            "pointer_mode": "mouse",
            "hidden": hidden,
            "restore_position": original_position if restore_cursor else None,
        }
        return True

    def pointer_session_active(self, session_id: str) -> bool:
        session = self._pointer_sessions.get(session_id)
        if session is None:
            return False
        target_window = session.get("target_window")
        if target_window and not self._window_is_available(target_window):
            return False
        if session.get("pointer_mode") == "touch":
            return True
        target = str(session.get("foreground_process") or "")
        foreground = self._foreground_window()
        if not foreground:
            return True
        return not target or self._window_process_matches(foreground, target)

    def move_pointer_session(self, session_id: str, dx: int = 0, dy: int = 0) -> bool:
        session = self._pointer_sessions.get(session_id)
        if session is None:
            return False
        if session.get("pointer_mode") != "touch":
            self.move(dx, dy)
            return True
        point = session.get("touch_point")
        bounds = session.get("touch_bounds")
        if not isinstance(point, tuple) or not isinstance(bounds, tuple):
            return False
        x, y = int(point[0]), int(point[1])
        left, top, right, bottom = (int(value) for value in bounds)
        next_x = x + int(dx)
        next_y = y + int(dy)
        margin = 24
        if next_x <= left + margin or next_x >= right - margin or next_y <= top + margin or next_y >= bottom - margin:
            if session.get("touch_active"):
                self._inject_touch(x, y, "up")
            center = self._window_client_center(session.get("target_window"))
            if center is None:
                return False
            x, y = center
            next_x = x + int(dx)
            next_y = y + int(dy)
            session["touch_active"] = False
        if not session.get("touch_active"):
            if not self._inject_touch(x, y, "down"):
                return False
            session["touch_active"] = True
        if not self._inject_touch(next_x, next_y, "update"):
            return False
        session["touch_point"] = (next_x, next_y)
        return True

    def end_pointer_session(self, session_id: str) -> None:
        session = self._pointer_sessions.pop(session_id, None)
        if session is None:
            return
        if session.get("pointer_mode") == "touch":
            point = session.get("touch_point")
            if session.get("touch_active") and isinstance(point, tuple):
                self._inject_touch(int(point[0]), int(point[1]), "up")
            return
        restore_position = session.get("restore_position")
        if isinstance(restore_position, tuple) and len(restore_position) == 2:
            self.move_absolute(int(restore_position[0]), int(restore_position[1]))
        if session.get("hidden"):
            self._set_cursor_visible(True)

    @staticmethod
    def _foreground_window() -> Any:
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            get_foreground_window = ctypes.windll.user32.GetForegroundWindow
            get_foreground_window.restype = wintypes.HWND
            return get_foreground_window()
        except Exception:
            return None

    @classmethod
    def _foreground_process_matches(cls, expected: str) -> bool:
        if not expected:
            return True
        if sys.platform != "win32":
            return True
        hwnd = cls._foreground_window()
        return bool(hwnd and cls._window_process_matches(hwnd, expected))

    @classmethod
    def _window_process_matches(cls, hwnd: Any, expected: str) -> bool:
        actual = cls._window_process_name(hwnd)
        if not actual:
            return False
        actual_root = os.path.splitext(actual)[0]
        for candidate in cls._process_candidates(expected):
            expected_name = os.path.basename(candidate).lower()
            if actual == expected_name or actual_root == os.path.splitext(expected_name)[0]:
                return True
        return False

    @staticmethod
    def _window_process_name(hwnd: Any) -> str:
        if sys.platform != "win32" or not hwnd:
            return ""
        try:
            import ctypes
            from ctypes import wintypes

            process_id = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            process = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id.value)
            if not process:
                return False
            try:
                size = wintypes.DWORD(32768)
                path = ctypes.create_unicode_buffer(size.value)
                if not ctypes.windll.kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                    return ""
                return os.path.basename(path.value).lower()
            finally:
                ctypes.windll.kernel32.CloseHandle(process)
        except Exception:
            return ""

    @classmethod
    def _process_candidates(cls, expected: str) -> list[str]:
        return [name.strip() for name in str(expected).split("|") if name.strip()]

    @classmethod
    def _target_process_window(cls, expected: str) -> Any:
        if sys.platform != "win32" or not expected:
            return None
        for candidate in cls._process_candidates(expected):
            window = cls._find_process_window(candidate)
            if window:
                return window
        return None

    @classmethod
    def _find_process_window(cls, expected: str) -> Any:
        if sys.platform != "win32" or not expected:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            matches: list[Any] = []
            enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            @enum_callback
            def collect(hwnd: Any, _lparam: Any) -> bool:
                if ctypes.windll.user32.IsWindowVisible(hwnd) and cls._window_process_matches(hwnd, expected):
                    matches.append(hwnd)
                return True

            ctypes.windll.user32.EnumWindows(collect, 0)
            return matches[0] if matches else None
        except Exception:
            return None

    @staticmethod
    def _activate_window(hwnd: Any) -> None:
        if sys.platform != "win32" or not hwnd:
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)
            current_thread = kernel32.GetCurrentThreadId()
            foreground = user32.GetForegroundWindow()
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
            attached_threads: list[int] = []
            for thread_id in {target_thread, foreground_thread}:
                if thread_id and thread_id != current_thread and user32.AttachThreadInput(current_thread, thread_id, True):
                    attached_threads.append(thread_id)
            try:
                user32.AllowSetForegroundWindow(wintypes.DWORD(-1).value)
                user32.LockSetForegroundWindow(2)
                user32.ShowWindow(hwnd, 9)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetActiveWindow(hwnd)
                user32.SetFocus(hwnd)
            finally:
                for thread_id in attached_threads:
                    user32.AttachThreadInput(current_thread, thread_id, False)
        except Exception:
            return

    @staticmethod
    def _window_is_available(hwnd: Any) -> bool:
        if sys.platform != "win32":
            return True
        try:
            import ctypes

            return bool(ctypes.windll.user32.IsWindow(hwnd) and ctypes.windll.user32.IsWindowVisible(hwnd))
        except Exception:
            return False

    @classmethod
    def _foreground_client_center(cls) -> tuple[int, int] | None:
        return cls._window_client_center(cls._foreground_window())

    @staticmethod
    def _window_client_center(hwnd: Any) -> tuple[int, int] | None:
        if not hwnd:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
                return None
            point = wintypes.POINT(
                max(0, (rect.right - rect.left) // 2),
                max(0, (rect.bottom - rect.top) // 2),
            )
            if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point)):
                return None
            return int(point.x), int(point.y)
        except Exception:
            return None

    @staticmethod
    def _window_client_bounds(hwnd: Any) -> tuple[int, int, int, int] | None:
        if not hwnd:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
                return None
            top_left = wintypes.POINT(rect.left, rect.top)
            bottom_right = wintypes.POINT(rect.right, rect.bottom)
            if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(top_left)):
                return None
            if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
                return None
            return int(top_left.x), int(top_left.y), int(bottom_right.x), int(bottom_right.y)
        except Exception:
            return None

    def _initialize_touch_injection(self) -> bool:
        if self._touch_injection_ready:
            return True
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            from ctypes import wintypes

            class PointerInfo(ctypes.Structure):
                _fields_ = [
                    ("pointerType", ctypes.c_uint32),
                    ("pointerId", ctypes.c_uint32),
                    ("frameId", ctypes.c_uint32),
                    ("pointerFlags", ctypes.c_uint32),
                    ("sourceDevice", wintypes.HANDLE),
                    ("hwndTarget", wintypes.HWND),
                    ("ptPixelLocation", wintypes.POINT),
                    ("ptHimetricLocation", wintypes.POINT),
                    ("ptPixelLocationRaw", wintypes.POINT),
                    ("ptHimetricLocationRaw", wintypes.POINT),
                    ("dwTime", ctypes.c_uint32),
                    ("historyCount", ctypes.c_uint32),
                    ("InputData", ctypes.c_int32),
                    ("dwKeyStates", ctypes.c_uint32),
                    ("PerformanceCount", ctypes.c_uint64),
                    ("ButtonChangeType", ctypes.c_uint32),
                ]

            class PointerTouchInfo(ctypes.Structure):
                _fields_ = [
                    ("pointerInfo", PointerInfo),
                    ("touchFlags", ctypes.c_uint32),
                    ("touchMask", ctypes.c_uint32),
                    ("rcContact", wintypes.RECT),
                    ("rcContactRaw", wintypes.RECT),
                    ("orientation", ctypes.c_uint32),
                    ("pressure", ctypes.c_uint32),
                ]

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.InitializeTouchInjection.argtypes = [wintypes.UINT, wintypes.DWORD]
            user32.InitializeTouchInjection.restype = wintypes.BOOL
            user32.InjectTouchInput.argtypes = [wintypes.UINT, ctypes.POINTER(PointerTouchInfo)]
            user32.InjectTouchInput.restype = wintypes.BOOL
            self._touch_injection_ready = bool(user32.InitializeTouchInjection(1, 3))
            if self._touch_injection_ready:
                self._touch_user32 = user32
                self._touch_info_type = PointerTouchInfo
            return self._touch_injection_ready
        except Exception:
            return False

    def _inject_touch(self, x: int, y: int, phase: str) -> bool:
        if not self._initialize_touch_injection() or self._touch_user32 is None or self._touch_info_type is None:
            return False
        try:
            from ctypes import wintypes

            flags_by_phase = {
                "down": 0x00000002 | 0x00000004 | 0x00010000,
                "update": 0x00000002 | 0x00000004 | 0x00020000,
                "up": 0x00040000,
            }
            touch = self._touch_info_type()
            touch.pointerInfo.pointerType = 2
            touch.pointerInfo.pointerId = 1
            touch.pointerInfo.pointerFlags = flags_by_phase[phase]
            touch.pointerInfo.ptPixelLocation = wintypes.POINT(int(x), int(y))
            touch.pointerInfo.ptPixelLocationRaw = wintypes.POINT(int(x), int(y))
            touch.touchMask = 0x1 | 0x2 | 0x4
            touch.rcContact = wintypes.RECT(int(x) - 4, int(y) - 4, int(x) + 4, int(y) + 4)
            touch.rcContactRaw = touch.rcContact
            touch.orientation = 90
            touch.pressure = 32000
            import ctypes

            return bool(self._touch_user32.InjectTouchInput(1, ctypes.byref(touch)))
        except Exception:
            return False

    @staticmethod
    def _set_cursor_visible(visible: bool) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            ctypes.windll.user32.ShowCursor(bool(visible))
            return True
        except Exception:
            return False

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
        self.active_foreground_process = "3DViewer.exe"
        self.available_target_processes = {"3dviewer.exe", "view3d.exe"}
        self._pointer_sessions: dict[str, dict[str, Any]] = {}

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

    def tap_keys(self, tokens: list[str]) -> None:
        normalized = [normalize_key_token(token) for token in tokens if normalize_key_token(token)]
        self.events.append(("key_tap", tuple(normalized)))

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

    def begin_pointer_session(
        self,
        session_id: str,
        *,
        foreground_process: str = "",
        center_in_foreground: bool = False,
        hide_cursor: bool = False,
        restore_cursor: bool = False,
        pointer_mode: str = "",
        activate_foreground: bool = True,
    ) -> bool:
        candidates = {
            candidate.lower()
            for candidate in PynputInputBackend._process_candidates(foreground_process)
        }
        available_targets = {target.lower() for target in self.available_target_processes}
        if candidates and candidates.isdisjoint(available_targets):
            return False
        matched = next(iter(candidates & available_targets), foreground_process.split("|", 1)[0].strip())
        if matched and activate_foreground:
            self.active_foreground_process = matched
        elif matched and matched.lower() != self.active_foreground_process.lower():
            return False
        if session_id not in self._pointer_sessions:
            self._pointer_sessions[session_id] = {
                "foreground_process": matched,
                "pointer_mode": str(pointer_mode).strip().lower(),
            }
            self.events.append(
                (
                    "pointer_session_begin",
                    session_id,
                    matched,
                    bool(center_in_foreground),
                    bool(hide_cursor),
                    bool(restore_cursor),
                    str(pointer_mode),
                    bool(activate_foreground),
                )
            )
        return True

    def pointer_session_active(self, session_id: str) -> bool:
        session = self._pointer_sessions.get(session_id)
        if session is None:
            return False
        if session.get("pointer_mode") == "touch":
            target = str(session.get("foreground_process") or "")
            if not target:
                return True
            return target.lower() in {name.lower() for name in self.available_target_processes}
        target = str(session.get("foreground_process") or "")
        if not target:
            return True
        return target.lower() == self.active_foreground_process.lower()

    def move_pointer_session(self, session_id: str, dx: int = 0, dy: int = 0) -> bool:
        if session_id not in self._pointer_sessions:
            return False
        self.events.append(("pointer_session_move", session_id, int(dx), int(dy)))
        return True

    def end_pointer_session(self, session_id: str) -> None:
        if session_id in self._pointer_sessions:
            self._pointer_sessions.pop(session_id, None)
            self.events.append(("pointer_session_end", session_id))
