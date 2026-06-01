from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = Path(__file__).resolve().parent / "assets" / "generated"
PNG_PATH = GENERATED_DIR / "AirTrixx.png"
ICO_PATH = GENERATED_DIR / "AirTrixx.ico"
ICNS_PATH = GENERATED_DIR / "AirTrixx.icns"


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def create_base_icon(size: int = 1024) -> Image.Image:
    image = Image.new("RGBA", (size, size), "#0f766e")
    draw = ImageDraw.Draw(image)
    margin = size // 10
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size // 7,
        fill="#ffffff",
    )
    inner = margin + size // 16
    draw.rounded_rectangle(
        (inner, inner, size - inner, size - inner),
        radius=size // 9,
        fill="#111827",
    )
    accent = "#5eead4"
    for offset in (0, 90, 180):
        y = size // 2 - 170 + offset
        draw.line((size // 4, y, size * 3 // 4, y + 90), fill=accent, width=size // 38)
    font = _font(size // 3)
    text = "A"
    box = draw.textbbox((0, 0), text, font=font)
    text_w = box[2] - box[0]
    text_h = box[3] - box[1]
    draw.text(
        ((size - text_w) / 2, (size - text_h) / 2 - size // 24),
        text,
        fill="#ffffff",
        font=font,
    )
    return image


def write_icns(image: Image.Image) -> None:
    iconutil = shutil.which("iconutil")
    if not iconutil:
        return
    iconset = GENERATED_DIR / "AirTrixx.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    sizes = (16, 32, 64, 128, 256, 512)
    for size in sizes:
        resized = image.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(iconset / f"icon_{size}x{size}.png")
        if size <= 512:
            double = image.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
            double.save(iconset / f"icon_{size}x{size}@2x.png")
    subprocess.run([iconutil, "-c", "icns", str(iconset), "-o", str(ICNS_PATH)], check=True)


def main() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    image = create_base_icon()
    image.save(PNG_PATH)
    image.save(ICO_PATH, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    write_icns(image)
    print(f"Wrote {PNG_PATH}")
    print(f"Wrote {ICO_PATH}")
    if ICNS_PATH.exists():
        print(f"Wrote {ICNS_PATH}")
    else:
        print("Skipped .icns generation because iconutil is unavailable.")


if __name__ == "__main__":
    main()
