"""TikTok photo carousels — 1080×1920 JPEG slides (TikTok refuses PNG).

A carousel is NOT a product slideshow (Luc: ad-style doesn't work). It is a
useful "how I do it" post where the real pages are the proof. Facts come from
the subject's catalogue entry only. Posted as a draft through the photo
endpoint (MEDIA_UPLOAD, images pulled from obenpaper.com — verified prefix).

    python pin-studio/tiktok_carousel.py well-read-tbr [--outdir DIR]
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tiktok_story import CREAM, INK, MUTED, H, W, badge, books, font, hexrgb, text_block  # noqa: E402

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)


def page(img, path, y, width=940):
    pg = Image.open(path).convert("RGB")
    h = int(pg.height * width / pg.width)
    pg = pg.resize((width, h))
    frame = Image.new("RGBA", (width + 36, h + 36), (40, 34, 31, 255))
    frame.paste(pg, (18, 18))
    img.alpha_composite(frame, ((W - frame.width) // 2, y))
    return y + frame.height


def step(img, n, title, sub, acc):
    d = ImageDraw.Draw(img)
    d.ellipse((90, 300, 190, 400), fill=acc + (255,))
    d.text((140, 350), str(n), font=font("bold", 56), fill=(255, 255, 255, 255), anchor="mm")
    text_block(img, title, "serif", 78, INK, 520)
    text_block(img, sub, "sans", 44, MUTED, 655, maxw=820)


CAROUSELS = {
    "well-read-tbr": dict(
        product="Well Read", tag="reading journal", accent="#A94E28",
        slides=[
            ("hook", "how I'm finally reading my TBR pile next year", "a system, not a resolution"),
            ("step", 1, "Get the pile onto paper", "Every unread book you own, in one list.", "04.jpg"),
            ("step", 2, "One spine per book", "Fifty spines. Colour one each time you finish.", "03.jpg"),
            ("step", 3, "Goals, not streaks", "Goals for the year, on one page.", "02.jpg"),
            ("step", 4, "Log it lightly", "One line per book. That's it.", "06.jpg"),
            ("end",),
        ]),
}


def render(key, outdir):
    c = CAROUSELS[key]
    acc = hexrgb(c["accent"])
    prev = os.path.join(STUDIO, "previews", key.split("-tbr")[0] if key.startswith("well-read") else key, "tablet")
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for i, s in enumerate(c["slides"], 1):
        img = Image.new("RGBA", (W, H), CREAM + (255,))
        if s[0] == "hook":
            text_block(img, s[1], "italic", 104, INK, 560)
            text_block(img, s[2], "hand", 76, acc, 860)
            books(img, 390, 1420, 11, acc, seed=2)
            text_block(img, "swipe for the system", "bold", 48, MUTED, 1500)
        elif s[0] == "step":
            step(img, s[1], s[2], s[3], acc)
            page(img, os.path.join(prev, s[4]), 760)
        else:
            text_block(img, "the whole system lives in one journal", "italic", 76, INK, 520)
            page(img, os.path.join(prev, "01.jpg"), 660, width=760)
            text_block(img, f"{c['product']} · by Obenpaper", "bold", 58, INK, 1330)
            text_block(img, "tablet: 17 linked spreads", "sans", 40, MUTED, 1400)
            text_block(img, "print: A4 + US Letter", "sans", 40, MUTED, 1450)
            text_block(img, "search ObenPaper on Etsy", "bold", 50, acc, 1525)
        badge(img, c["product"], c["tag"], acc)
        p = os.path.join(outdir, f"{key}-{i:02d}.jpg")
        img.convert("RGB").save(p, quality=90)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key", choices=list(CAROUSELS))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "tiktok", "review"))
    a = ap.parse_args()
    print("\n".join(render(a.key, a.outdir)))


if __name__ == "__main__":
    main()
