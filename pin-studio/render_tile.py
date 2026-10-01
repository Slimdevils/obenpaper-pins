"""Render Obenpaper pin tiles (1000×1500 PNG) from the queue.

Run from the repo root or pin-studio/:

    python pin-studio/render_tile.py              # render every queued pin whose image is missing
    python pin-studio/render_tile.py --pin SP-7   # render (or re-render) one pin
    python pin-studio/render_tile.py --force      # re-render all unposted pins

Each pin in pinterest-api/pins_export.json carries a "subject" (a key in
catalogue.json) and a "tile" object:

    "tile": {
      "layout": "pages" | "tablet" | "type",
      "kicker":   "STUDENT PLANNER",          # small caps line, optional
      "headline": "Your whole year, one tap away",
      "subline":  "Dated + undated · tablet, A4, US Letter",
      "pages":    ["print/03.jpg", "print/05.jpg"],   # pages: 1–2 print pages; tablet: 1 tablet page
      "badge":    "Free · no sign-up"          # optional pill, type layout only
    }

The house look (md §01): DM Serif Display headlines, Poppins body, the
product's accent over its own soft tint, ink #3B302B text. The image goes to
pins/<image_file>, which the publisher turns into the public image URL.
"""

import argparse
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
QUEUE = os.path.join(ROOT, "pinterest-api", "pins_export.json")
POSTED = os.path.join(ROOT, "pinterest-api", "posted_ids.json")
PINS_DIR = os.path.join(ROOT, "pins")
CATALOGUE = os.path.join(STUDIO, "catalogue.json")
FONTS = os.path.join(STUDIO, "fonts")

W, H = 1000, 1500
MARGIN = 80
INK = "#3B302B"
INK2 = "#5C4F45"
MUTED = "#9A8C7C"
CREAM = "#FDF8F2"
WHITE = "#FFFFFF"


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


SERIF = "DMSerifDisplay-Regular.ttf"
SANS = "Poppins-Regular.ttf"
SANS_MED = "Poppins-Medium.ttf"


def rgb(hex_value):
    hex_value = hex_value.lstrip("#")
    return tuple(int(hex_value[i:i + 2], 16) for i in (0, 2, 4))


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def fit(draw, text, face, sizes, width, max_lines):
    """Largest size from `sizes` at which `text` fits in max_lines."""
    for size in sizes:
        fnt = font(face, size)
        lines = wrap(draw, text, fnt, width)
        if len(lines) <= max_lines and all(draw.textlength(l, font=fnt) <= width for l in lines):
            return fnt, lines
    raise ValueError(f"text does not fit in {max_lines} lines even at {sizes[-1]}px: {text!r}")


def draw_lines(draw, lines, fnt, x, y, fill, leading):
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += leading
    return y


def spaced(draw, xy, text, fnt, fill, tracking):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking
    return x


def shadowed(canvas, img, xy, angle=0.0, radius=26, opacity=70, offset=(0, 18)):
    """Paste img with a soft shadow, optionally rotated."""
    if angle:
        img = img.convert("RGBA").rotate(angle, resample=Image.BICUBIC, expand=True)
    else:
        img = img.convert("RGBA")
    alpha = img.split()[-1]
    shadow = Image.new("RGBA", img.size, (40, 30, 25, 0))
    shadow.putalpha(alpha.point(lambda a: opacity if a else 0))
    pad = radius * 3
    layer = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    layer.paste(shadow, (pad, pad), shadow)
    layer = layer.filter(ImageFilter.GaussianBlur(radius))
    x, y = xy
    canvas.alpha_composite(layer, (int(x - pad + offset[0]), int(y - pad + offset[1])))
    canvas.alpha_composite(img, (int(x), int(y)))


def load_page(subject, rel):
    folder = subject.get("previews")
    candidates = [folder] + ([subject["previews_extra"]] if subject.get("previews_extra") else [])
    for base in candidates:
        path = os.path.join(STUDIO, base, rel)
        if base and os.path.exists(path):
            return Image.open(path).convert("RGB")
    raise FileNotFoundError(f"no preview '{rel}' for {subject['key']} (looked in {candidates})")


def text_block(draw, tile, accent, top):
    """Kicker, headline, subline. Returns the y below the block."""
    y = top
    kicker = (tile.get("kicker") or "").upper()
    if kicker:
        spaced(draw, (MARGIN, y), kicker, font(SANS_MED, 26), accent["dark"], 3.2)
        y += 58
    # Two lines at most: a third line shrinks the product image too far (seen on
    # the first batch, 1 Oct 2026). A longer headline is refused, not squeezed.
    fnt, lines = fit(draw, tile["headline"], SERIF, range(92, 66, -4), W - 2 * MARGIN, 2)
    y = draw_lines(draw, lines, fnt, MARGIN, y, INK, int(fnt.size * 1.08))
    if tile.get("subline"):
        y += 22
        sfnt, slines = fit(draw, tile["subline"], SANS, range(34, 25, -2), W - 2 * MARGIN, 2)
        y = draw_lines(draw, slines, sfnt, MARGIN, y, INK2, int(sfnt.size * 1.45))
    return y


def footer(draw, accent, right_text):
    y = H - 112
    draw.line([(MARGIN, y), (W - MARGIN, y)], fill=accent["main"], width=3)
    draw.text((MARGIN, y + 24), "obenpaper", font=font(SERIF, 44), fill=INK)
    rfnt = font(SANS_MED, 24)
    tw = draw.textlength(right_text, font=rfnt)
    draw.text((W - MARGIN - tw, y + 38), right_text, font=rfnt, fill=accent["dark"])


def layout_pages(canvas, subject, tile, top, bottom):
    pages = tile.get("pages") or []
    if not 1 <= len(pages) <= 2:
        raise ValueError("pages layout takes 1 or 2 print pages")
    box_h = bottom - top
    imgs = [load_page(subject, p) for p in pages]
    if len(imgs) == 1:
        page_h = int(box_h * 0.94)
        im = imgs[0].resize((int(imgs[0].width * page_h / imgs[0].height), page_h), Image.LANCZOS)
        shadowed(canvas, im, ((W - im.width) / 2, top + (box_h - page_h) / 2))
        return
    # Two pages, fanned, kept inside the side margins: the pair spans
    # 1.55 page-widths, so size the pages from the available width as well.
    ratio = imgs[0].width / imgs[0].height
    page_w = min(int((W - 2 * MARGIN + 30) / 1.6), int(box_h * 0.86 * ratio))
    page_h = int(page_w / ratio)
    back, front = (im.resize((page_w, int(page_w * im.height / im.width)), Image.LANCZOS) for im in imgs)
    left = (W - page_w * 1.55) / 2
    shadowed(canvas, back, (left - 12, top), angle=3.5, opacity=55)
    shadowed(canvas, front, (left + page_w * 0.55, top + box_h - front.height - 10), angle=-2.5)


def layout_tablet(canvas, subject, tile, accent, top, bottom):
    pages = tile.get("pages") or []
    if len(pages) != 1:
        raise ValueError("tablet layout takes exactly 1 tablet page")
    page = load_page(subject, pages[0])
    bezel = 26
    max_w = W - 2 * MARGIN + 40
    box_h = bottom - top
    inner_w = max_w - 2 * bezel
    inner_h = int(inner_w * page.height / page.width)
    if inner_h + 2 * bezel > box_h:
        inner_h = box_h - 2 * bezel
        inner_w = int(inner_h * page.width / page.height)
    page = page.resize((inner_w, inner_h), Image.LANCZOS)
    frame = Image.new("RGBA", (inner_w + 2 * bezel, inner_h + 2 * bezel), (0, 0, 0, 0))
    fdraw = ImageDraw.Draw(frame)
    fdraw.rounded_rectangle([0, 0, frame.width - 1, frame.height - 1], radius=44, fill=INK)
    mask = Image.new("L", page.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, inner_w - 1, inner_h - 1], radius=14, fill=255)
    frame.paste(page, (bezel, bezel), mask)
    x = (W - frame.width) / 2
    y = top + (box_h - frame.height) / 2
    shadowed(canvas, frame, (x, y), radius=30, opacity=80)


def layout_type(canvas, draw, subject, tile, accent, top, bottom):
    """Typographic card for site pages and tools — no product imagery."""
    card = [MARGIN, top + 10, W - MARGIN, bottom]
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([c + (0, 16, 0, 16)[i] for i, c in enumerate(card)],
                                             radius=36, fill=(40, 30, 25, 60))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24)))
    draw.rounded_rectangle(card, radius=36, fill=WHITE)
    draw.rounded_rectangle([card[0], card[1], card[2], card[1] + 18], radius=9, fill=accent["main"])

    x0, y = card[0] + 56, card[1] + 80
    width = card[2] - card[0] - 112
    name = tile.get("card_title") or subject["facts"][0].split(" — ")[0]
    nfnt, nlines = fit(draw, name, SERIF, range(64, 40, -4), width, 2)
    y = draw_lines(draw, nlines, nfnt, x0, y, accent["dark"], int(nfnt.size * 1.1))
    y += 26
    body = tile.get("card_text") or ""
    if body:
        bfnt, blines = fit(draw, body, SANS, range(32, 23, -1), width, 6)
        y = draw_lines(draw, blines, bfnt, x0, y, INK2, int(bfnt.size * 1.5))

    # Decorative "input → result" rows: neutral shapes, no numbers, no claims.
    rows_top = max(y + 46, card[1] + 330)
    row_h = 74
    for i in range(3):
        ry = rows_top + i * (row_h + 20)
        if ry + row_h > card[3] - 170:
            break
        draw.rounded_rectangle([x0, ry, card[2] - 56, ry + row_h], radius=16,
                               fill=accent["bg"] if accent["bg"].upper() != CREAM else "#F3ECE3")
        draw.rounded_rectangle([x0 + 24, ry + 26, x0 + 24 + 160 + i * 50, ry + 48], radius=11,
                               fill=accent["main"] if i == 2 else "#D9CFC4")

    badge = tile.get("badge") or "Free · no sign-up"
    bfnt = font(SANS_MED, 30)
    bw = draw.textlength(badge, font=bfnt) + 72
    by = card[3] - 120
    draw.rounded_rectangle([x0, by, x0 + bw, by + 72], radius=36, fill=accent["main"])
    draw.text((x0 + 36, by + 17), badge, font=bfnt, fill=WHITE if _dark(accent["main"]) else INK)


def _dark(hex_value):
    r, g, b = rgb(hex_value)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 160


def render(pin, subject, out_path):
    tile = pin["tile"]
    accent = subject["accent"]
    canvas = Image.new("RGBA", (W, H), rgb(accent["bg"]) + (255,))
    draw = ImageDraw.Draw(canvas)

    text_bottom = text_block(draw, tile, accent, MARGIN)
    top, bottom = text_bottom + 56, H - 150
    if bottom - top < 520:
        raise ValueError("text block too tall — shorten the headline or subline")

    layout = tile.get("layout", "pages")
    if layout == "pages":
        layout_pages(canvas, subject, tile, top, bottom)
    elif layout == "tablet":
        layout_tablet(canvas, subject, tile, accent, top, bottom)
    elif layout == "type":
        layout_type(canvas, draw, subject, tile, accent, top, bottom)
    else:
        raise ValueError(f"unknown layout {layout}")

    draw = ImageDraw.Draw(canvas)
    footer(draw, accent, tile.get("footer") or "obenpaper.com")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


def load_catalogue():
    with open(CATALOGUE, "r", encoding="utf-8") as fh:
        return {s["key"]: s for s in json.load(fh)["subjects"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", help="render one pin by id (always re-renders it)")
    parser.add_argument("--force", action="store_true", help="re-render every unposted pin")
    args = parser.parse_args()

    catalogue = load_catalogue()
    with open(QUEUE, "r", encoding="utf-8") as fh:
        pins = json.load(fh)
    posted = set()
    if os.path.exists(POSTED):
        with open(POSTED, "r", encoding="utf-8") as fh:
            posted = {e["pin"] for e in json.load(fh)}

    done = 0
    for pin in pins:
        if "tile" not in pin or pin["id"] in posted:
            continue
        if args.pin and pin["id"] != args.pin:
            continue
        out = os.path.join(PINS_DIR, pin["image_file"])
        if os.path.exists(out) and not (args.force or args.pin):
            continue
        subject = catalogue.get(pin.get("subject"))
        if not subject:
            sys.exit(f"{pin['id']}: subject '{pin.get('subject')}' is not in catalogue.json")
        render(pin, subject, out)
        print(f"rendered {os.path.relpath(out, ROOT)}")
        done += 1
    print(f"{done} tile(s) rendered.")


if __name__ == "__main__":
    main()
