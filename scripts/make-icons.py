#!/usr/bin/env python3
"""Generate favicon + PWA icons from portal/assets/logo.png (run on server)."""
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("pip install pillow")

ROOT = Path(__file__).resolve().parents[1] / "portal" / "assets"
SRC = ROOT / "logo.png"
if not SRC.exists():
    raise SystemExit(f"missing {SRC}")

img = Image.open(SRC).convert("RGBA")


def fit_square(size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    copy = img.copy()
    copy.thumbnail((size - size // 10, size - size // 10), Image.Resampling.LANCZOS)
    x = (size - copy.width) // 2
    y = (size - copy.height) // 2
    canvas.paste(copy, (x, y), copy)
    return canvas


fit_square(32).save(ROOT / "favicon.png", format="PNG")
fit_square(180).save(ROOT / "apple-touch-icon.png", format="PNG")
fit_square(192).save(ROOT / "icon-192.png", format="PNG")
fit_square(512).save(ROOT / "icon-512.png", format="PNG")
print("icons written to", ROOT)
