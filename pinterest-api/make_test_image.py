"""Generate the disposable 1000x1500 test PNG for the Trial/demo-video run.

Run:  python make_test_image.py

Writes images/test-pin.png — plain cream background, the word TEST. This is
deliberately not a real product tile: it goes to the zz-api-test scratch
board and gets deleted afterwards.
"""

import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "images")
OUT_PATH = os.path.join(OUT_DIR, "test-pin.png")

CREAM = "#FDF8F2"
INK = "#3B302B"


def load_font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    img = Image.new("RGB", (1000, 1500), CREAM)
    draw = ImageDraw.Draw(img)
    font = load_font(160)

    text = "TEST"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((1000 - (right - left)) / 2 - left, (1500 - (bottom - top)) / 2 - top),
        text,
        fill=INK,
        font=font,
    )

    img.save(OUT_PATH, "PNG")
    print(f"Wrote {OUT_PATH} ({img.width}x{img.height})")


if __name__ == "__main__":
    main()
