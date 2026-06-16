from __future__ import annotations

from typing import Any

from app_controller import AirTrixxController


class AirTrixxWebAPI:
    """Small pywebview bridge consumed by the local HTML frontend."""

    def __init__(self, controller: AirTrixxController) -> None:
        self.controller = controller

    def get_bootstrap(self) -> dict[str, Any]:
        return self.controller.get_state()

    def get_state(self) -> dict[str, Any]:
        return self.controller.get_state()

    def dispatch(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.controller.dispatch(action, payload)

    def get_camera_frame(self, max_width: int = 960, max_height: int = 540) -> dict[str, Any]:
        return self.controller.get_camera_frame(max_width=max_width, max_height=max_height)

    def close(self) -> dict[str, bool]:
        self.controller.close()
        return {"ok": True}
