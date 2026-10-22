"""Build and render flip-through videos (MP4) in the pin tiles' house look.

Used two ways:

  1. Video pins. A draft whose tile has "layout": "video" becomes a 1000×1500
     MP4 plus a PNG cover (studio.py add → render_pin_video). The tile fields
     are the same as an image tile: kicker, headline, subline, and "pages" —
     here 3 to 5 pages of ONE edition, e.g. ["tablet/01.jpg", "tablet/04.jpg",
     "tablet/07.jpg"]. Tablet pages slide in a tablet frame; print pages
     change on a sheet of paper, like the site's preview viewer.

  2. Listing videos for Etsy/Payhip (listing_video.py): square 1080×1080 or
     landscape 1920×1080, built from the site's own preview pages.

The text is fitted here with exactly the tiles' fit() (same fonts, sizes and
two-line limit), so a headline that would not fit a tile does not fit a video
either. The geometry is computed here too; pin-studio/video/ only draws it.

Rendering needs Node and `npm ci --prefix pin-studio/video` once per checkout.

To look at a rendered video, pull a few frames out as PNGs:

    python pin-studio/video_spec.py frames pins/<id>.mp4          # at 1 s, 5 s and 9 s
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

from render_tile import CREAM, FONTS, INK, INK2, SANS, SERIF, STUDIO, fit, load_page

VIDEO_DIR = os.path.join(STUDIO, "video")

FORMATS = {
    # Pinterest: the same 2:3 as the image tiles.
    "pin": (1000, 1500),
    # Etsy / Payhip listing videos.
    "square": (1080, 1080),
    "landscape": (1920, 1080),
}

TIMING = {"intro": 36, "perPage": 66, "outro": 30}  # frames at 30 fps
MIN_PAGES, MAX_PAGES = 3, 5


def _measure():
    return ImageDraw.Draw(Image.new("RGB", (10, 10)))


def _text(kicker, headline, subline, x, y, width, sizes):
    """Kicker / headline / subline fitted like a tile. Returns (layout, bottom)."""
    draw = _measure()
    k_size, k_gap, h_sizes, h_lines, s_sizes = sizes
    out = {}
    if kicker:
        out["kicker"] = {"text": kicker.upper(), "size": k_size, "tracking": round(k_size * 0.12, 1), "x": x, "y": y}
        y += k_gap
    hfnt, hl = fit(draw, headline, SERIF, h_sizes, width, h_lines)
    lead = int(hfnt.size * 1.08)
    out["headline"] = {"lines": hl, "size": hfnt.size, "leading": lead, "x": x, "y": y}
    y += lead * len(hl)
    if subline:
        y += int(hfnt.size * 0.24)
        sfnt, sl = fit(draw, subline, SANS, s_sizes, width, 2)
        slead = int(sfnt.size * 1.45)
        out["subline"] = {"lines": sl, "size": sfnt.size, "leading": slead, "x": x, "y": y}
        y += slead * len(sl)
    return out, y


def layout_for(fmt, kicker, headline, subline, footer_right):
    W, H = FORMATS[fmt]
    if fmt == "pin":
        m = 80
        text, bottom = _text(kicker, headline, subline, m, m, W - 2 * m,
                             (26, 58, range(92, 66, -4), 2, range(34, 25, -2)))
        media = {"x": m - 20, "y": bottom + 56, "w": W - 2 * m + 40, "h": (H - 190) - (bottom + 56)}
        footer = {"y": H - 112, "x0": m, "x1": W - m, "wordmarkSize": 44, "rightSize": 24}
        dots = {"y": H - 172, "size": 12}
        min_media = 560
    elif fmt == "square":
        m = 64
        text, bottom = _text(kicker, headline, subline, m, m, W - 2 * m,
                             (22, 46, range(68, 44, -4), 2, range(28, 21, -1)))
        media = {"x": m, "y": bottom + 36, "w": W - 2 * m, "h": (H - 150) - (bottom + 36)}
        footer = {"y": H - 96, "x0": m, "x1": W - m, "wordmarkSize": 36, "rightSize": 20}
        dots = {"y": H - 132, "size": 10}
        min_media = 480
    else:  # landscape: words on the left, pages on the right
        m = 96
        col = 640
        text, bottom = _text(kicker, headline, subline, m, 170, col,
                             (24, 54, range(84, 52, -4), 3, range(30, 22, -1)))
        media = {"x": m + col + 64, "y": 90, "w": W - (m + col + 64) - m, "h": H - 90 - 190}
        footer = {"y": H - 104, "x0": m, "x1": W - m, "wordmarkSize": 40, "rightSize": 22}
        dots = {"y": H - 162, "size": 11}
        min_media = 600
    if media["h"] < min_media:
        raise ValueError("text block too tall for the video — shorten the headline or subline")
    footer["right"] = footer_right or ""
    return {"width": W, "height": H, "media": media, "footer": footer, "dots": dots, **text}


def build_spec(fmt, accent, kicker, headline, subline, page_paths, footer_right="obenpaper.com", edition=None):
    """A complete render spec. page_paths: absolute paths, all one edition.

    The edition is read from the pages' folder (print/ or tablet/) unless
    given — the site's "flat" previews keep it in the file name instead."""
    if not MIN_PAGES <= len(page_paths) <= MAX_PAGES:
        raise ValueError(f"a video takes {MIN_PAGES}–{MAX_PAGES} pages, got {len(page_paths)}")
    editions = {edition} if edition else {os.path.basename(os.path.dirname(p)) for p in page_paths}
    if len(editions) != 1 or editions - {"print", "tablet"}:
        raise ValueError("video pages must all come from one edition: all print/ or all tablet/")
    pages = []
    for p in page_paths:
        if not os.path.exists(p):
            raise FileNotFoundError(f"no page {p}")
        with Image.open(p) as im:
            pages.append({"path": os.path.abspath(p), "width": im.width, "height": im.height})
    W, H = FORMATS[fmt]
    return {
        "fontsDir": FONTS,
        "pages": pages,
        "props": {
            "width": W,
            "height": H,
            "edition": editions.pop(),
            "timing": TIMING,
            "colors": {"bg": accent["bg"], "main": accent["main"], "dark": accent["dark"],
                       "ink": INK, "ink2": INK2, "cream": CREAM},
            "layout": layout_for(fmt, kicker, headline, subline, footer_right),
        },
    }


def render(spec, mp4_out, png_out=None):
    """Render the spec with Remotion. Raises RuntimeError with the fix if Node is missing."""
    if not shutil.which("node"):
        raise RuntimeError("Node is not installed — video tiles need Node 18+")
    if not os.path.isdir(os.path.join(VIDEO_DIR, "node_modules")):
        raise RuntimeError("run `npm ci --prefix pin-studio/video` once, then try again")
    os.makedirs(os.path.dirname(os.path.abspath(mp4_out)), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
        spec_path = fh.name
    cmd = ["node", os.path.join(VIDEO_DIR, "render.mjs"), "--spec", spec_path, "--out", os.path.abspath(mp4_out)]
    if png_out:
        cmd += ["--poster", os.path.abspath(png_out)]
    try:
        result = subprocess.run(cmd, cwd=VIDEO_DIR, capture_output=True, text=True)
    finally:
        os.remove(spec_path)
    if result.returncode != 0:
        raise RuntimeError(f"video render failed:\n{result.stderr[-2000:]}")
    return mp4_out


def render_pin_video(pin, subject, mp4_out, png_out):
    """A video pin: 1000×1500 MP4 and its PNG cover, from the catalogue subject."""
    tile = pin["tile"]
    pages = tile.get("pages") or []
    paths = []
    for rel in pages:
        load_page(subject, rel)  # same lookup and error as image tiles
        for base in [subject.get("previews"), subject.get("previews_extra")]:
            if base and os.path.exists(os.path.join(STUDIO, base, rel)):
                paths.append(os.path.join(STUDIO, base, rel))
                break
    spec = build_spec("pin", subject["accent"], tile.get("kicker", ""), tile["headline"],
                      tile.get("subline", ""), paths, tile.get("footer") or "obenpaper.com")
    return render(spec, mp4_out, png_out)


def _ffmpeg():
    """System ffmpeg, else the one Remotion ships with (no install needed)."""
    found = shutil.which("ffmpeg")
    if found:
        return found, None
    for exe in glob.glob(os.path.join(VIDEO_DIR, "node_modules", "@remotion", "compositor-*", "ffmpeg")):
        return exe, os.path.dirname(exe)
    raise RuntimeError("no ffmpeg — run `npm ci --prefix pin-studio/video` first")


def frames(mp4, times=(1, 5, 9), out_dir=None):
    """Save frames of `mp4` at the given seconds as PNGs; return their paths."""
    exe, libs = _ffmpeg()
    env = dict(os.environ)
    if libs:
        env["LD_LIBRARY_PATH"] = libs + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    out_dir = out_dir or tempfile.mkdtemp(prefix="obp-frames-")
    stem = os.path.splitext(os.path.basename(mp4))[0]
    paths = []
    for t in times:
        out = os.path.join(out_dir, f"{stem}-{t}s.png")
        subprocess.run([exe, "-loglevel", "error", "-y", "-ss", str(t), "-i", mp4, "-frames:v", "1", out],
                       check=True, env=env)
        paths.append(out)
    return paths


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "frames":
        for path in frames(sys.argv[2], tuple(float(t) for t in sys.argv[3:]) or (1, 5, 9)):
            print(path)
    else:
        sys.exit("usage: python pin-studio/video_spec.py frames <video.mp4> [seconds ...]")
