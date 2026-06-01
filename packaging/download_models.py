from __future__ import annotations

import ssl
import urllib.request
from pathlib import Path


GENERATED_DIR = Path(__file__).resolve().parent / "assets" / "generated"
HAND_LANDMARKER_MODEL = GENERATED_DIR / "hand_landmarker.task"
HAND_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def download(url: str, target: Path) -> None:
    if target.exists() and target.stat().st_size > 0:
        print(f"Using existing {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    context = _ssl_context()
    with urllib.request.urlopen(url, timeout=60, context=context) as response:
        target.write_bytes(response.read())
    print(f"Downloaded {target}")


def main() -> None:
    download(HAND_LANDMARKER_URL, HAND_LANDMARKER_MODEL)


if __name__ == "__main__":
    main()
