"""Regenerate desktop/icon.ico (multi-resolution) -- a phone-case silhouette on the app's dark tile.
Run: python desktop/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "icon.ico"
S = 256


def draw(size: int = S) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = size / S
    d.rounded_rectangle([8 * k, 8 * k, 248 * k, 248 * k], radius=52 * k, fill=(15, 23, 42, 255),
                        outline=(34, 211, 238, 255), width=max(1, round(6 * k)))
    # case (bumper) and phone back
    d.rounded_rectangle([76 * k, 34 * k, 180 * k, 222 * k], radius=26 * k, fill=(20, 184, 166, 255))
    d.rounded_rectangle([88 * k, 46 * k, 168 * k, 210 * k], radius=17 * k, fill=(8, 47, 73, 255))
    # camera island
    d.rounded_rectangle([96 * k, 54 * k, 136 * k, 96 * k], radius=10 * k, fill=(34, 211, 238, 255))
    d.ellipse([104 * k, 62 * k, 128 * k, 86 * k], fill=(8, 47, 73, 255))
    # buttons
    d.rounded_rectangle([180 * k, 84 * k, 188 * k, 120 * k], radius=3 * k, fill=(249, 115, 22, 255))
    return img


if __name__ == "__main__":
    base = draw(S)
    base.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"wrote {OUT}")
