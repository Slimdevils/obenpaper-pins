"""TikTok story videos — 1080×1920, voice-over, NO music (Luc, 12 Nov 2026).

Three stories, rebuilt from the 8 Nov concepts with the reviewer's fixes:
  * the WHOLE hook is on screen from frame 1 (no word-by-word build-up)
  * no end card longer than ~1 s — a small product badge instead
  * a ~1 s flash of a REAL inside page, so the product is actually seen
  * slogans vary (no "2027: …" on everything)
  * text stays out of TikTok's UI: bottom ~350 px, right ~150 px, top ~140 px
  * no prices on screen

Each scene lasts as long as its voice-over line (+ a breath). Without
--vo the line lengths are estimated and the video is silent (preview only).

    python pin-studio/tiktok_story.py <story> [--vo MODEL_DIR] [--out PATH]
    python pin-studio/tiktok_story.py all --vo MODEL_DIR --outdir tiktok/videos
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
W, H, FPS = 1080, 1920, 30
SAFE_L, SAFE_R, SAFE_T, SAFE_B = 90, W - 170, 150, H - 380

CREAM, INK, MUTED = (253, 248, 242), (59, 48, 43), (122, 108, 100)
FONT = {k: os.path.join(STUDIO, "fonts", f) for k, f in {
    "serif": "DMSerifDisplay-Regular.ttf", "italic": "DMSerifDisplay-Italic.ttf",
    "sans": "Poppins-Medium.ttf", "bold": "Poppins-SemiBold.ttf", "hand": "Caveat-Variable.ttf"}.items()}


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def font(kind, size, _c={}):
    if (kind, size) not in _c:
        _c[(kind, size)] = ImageFont.truetype(FONT[kind], size)
    return _c[(kind, size)]


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def pop(t):
    t = max(0.0, min(1.0, t))
    return 1 + 0.12 * math.sin(t * math.pi) * (1 - t)


def wrap(d, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def text_block(img, text, kind, size, color, cy, alpha=1.0, maxw=None, spacing=1.12, scale=1.0):
    """Centred, wrapped text whose vertical centre sits at cy (inside the safe zone)."""
    if alpha <= 0:
        return
    maxw = maxw or (SAFE_R - SAFE_L)
    size = max(8, int(size * scale))
    f = font(kind, size)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = wrap(d, text, f, maxw)
    lh = size * spacing
    y = cy - lh * len(lines) / 2
    cx = (SAFE_L + SAFE_R) / 2
    for ln in lines:
        d.text((cx, y + lh / 2), ln, font=f, fill=color + (int(255 * alpha),), anchor="mm")
        y += lh
    img.alpha_composite(layer)


def badge(img, name, line, accent, alpha=1.0):
    """Small persistent product tag, top-left, so even a loop names the product."""
    if alpha <= 0:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f1, f2 = font("bold", 34), font("sans", 28)
    w = max(d.textlength(name, font=f1), d.textlength(line, font=f2)) + 56
    x, y = SAFE_L, SAFE_T
    d.rounded_rectangle((x, y, x + w, y + 104), 26, fill=accent + (int(235 * alpha),))
    d.text((x + 28, y + 18), name, font=f1, fill=(255, 255, 255, int(255 * alpha)))
    d.text((x + 28, y + 60), line, font=f2, fill=(255, 255, 255, int(220 * alpha)))
    img.alpha_composite(layer)


def find_us(img, product, t):
    """Last 1–2 s: how to find it — the bio link is not clickable yet."""
    a = ease((t - 0.3) / 0.3)
    text_block(img, f"{product} · by Obenpaper", "bold", 52, INK, 1370, alpha=a)
    text_block(img, "search ObenPaper on Etsy", "sans", 44, MUTED, 1445, alpha=a)


def page_flash(img, path, t, accent):
    """The real inside page slides up on a tablet-ish frame (~1 s)."""
    pg = Image.open(path).convert("RGB")
    k = ease(t / 0.35)
    pw = 900
    ph = int(pg.height * pw / pg.width)
    pg = pg.resize((pw, ph))
    frame = Image.new("RGBA", (pw + 40, ph + 40), (40, 34, 31, 255))
    frame.paste(pg, (20, 20))
    x = (W - frame.width) // 2
    y = int(560 + (1 - k) * 300)
    shade = Image.new("RGBA", img.size, accent + (int(40 * k),))
    img.alpha_composite(shade)
    img.alpha_composite(frame, (x, y))


def books(img, x0, base_y, n, accent, seed=0, width=300, alpha=1.0):
    """A stack of n book spines, bottom at base_y."""
    if n <= 0:
        return
    tones = [accent, tuple(int(c * 0.75) for c in accent), (205, 170, 140), (120, 96, 84), (230, 205, 180)]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y = base_y
    for i in range(int(n)):
        h = 34 + ((i * 7 + seed) % 3) * 8
        off = ((i * 13 + seed) % 5 - 2) * 9
        w = width - ((i * 11 + seed) % 4) * 18
        x = x0 + (width - w) // 2 + off
        d.rounded_rectangle((x, y - h, x + w, y), 6, fill=tones[(i + seed) % len(tones)] + (int(255 * alpha),))
        d.line((x + 18, y - h / 2, x + w - 18, y - h / 2), fill=(255, 255, 255, int(70 * alpha)), width=2)
        y -= h + 2
    img.alpha_composite(layer)


# ---------------------------------------------------------------- stories
# Each scene: (voice-over line, draw(img, t, dur)). The badge is drawn on every
# frame by the renderer.

def story_one_more_chapter():
    acc = hexrgb("#A94E28")
    page = os.path.join(STUDIO, "previews", "well-read", "tablet", "06.jpg")
    times = ["10:00 PM", "11:30 PM", "1:00 AM", "3:14 AM"]
    pages = [12, 96, 188, 340]
    lines = ["It's ten p.m.... just one more chapter.",
             "Eleven thirty? Okay, okay. One more.",
             "One a.m. This is the last one. I promise.",
             "Three fourteen a.m.... okay. One. More.",
             "Every book you couldn't put down? Keep it in Well Read."]

    def scene(i):
        def draw(img, t, dur):
            text_block(img, "one more chapter", "italic", 92, INK, 470)
            prev = pages[i - 1] if i else 0
            k = ease(t / max(0.6, dur * 0.7))
            text_block(img, times[i], "serif", 190, acc, 760, scale=pop(t / 0.4))
            text_block(img, f"page {int(prev + (pages[i] - prev) * k)}", "bold", 92, INK, 1010)
            text_block(img, ["(it's fine)", "(still fine)", "(work is at 8)", "okay ONE more."][i],
                       "hand", 96 if i == 3 else 78, acc if i == 3 else MUTED, 1230)
        return draw

    def end(img, t, dur):
        page_flash(img, page, t, acc)
        text_block(img, "every book you couldn't put down", "italic", 64, INK, 420, alpha=ease(t / 0.3))
        find_us(img, "Well Read", t)
    return dict(slug="one-more-chapter", product="Well Read", tag="reading journal", accent=acc,
                scenes=[(lines[i], scene(i)) for i in range(4)] + [(lines[4], end)])


def story_me_at_9am():
    acc = hexrgb("#0E5F7E")
    page = os.path.join(STUDIO, "previews", "well-spent", "tablet", "05.jpg")
    beats = [("me at 9am:", "this month I'm saving."),
             ("12pm:", "it's just a coffee."),
             ("4pm:", "I deserve a little treat."),
             ("11pm:", "where did it all go??")]
    lines = ["Me, at nine a.m.? This month, I'm saving.",
             "Twelve p.m.... it's just a coffee!",
             "Four p.m.? Honestly... I deserve a little treat.",
             "Eleven p.m.... wait. Where did it all go?",
             "So, write down where you stand. With Well Spent."]

    def scene(i):
        def draw(img, t, dur):
            for j in range(i + 1):
                faded = j < i
                text_block(img, beats[j][0], "bold", 62, MUTED if faded else acc, 450 + j * 260,
                           alpha=0.45 if faded else ease(t / 0.2))
                text_block(img, beats[j][1], "serif", 80 if not faded else 60, INK, 450 + j * 260 + 105,
                           alpha=0.45 if faded else ease(t / 0.25), scale=1.0 if faded else pop(t / 0.4))
        return draw

    def end(img, t, dur):
        page_flash(img, page, t, acc)
        text_block(img, "write down where you stand", "italic", 66, INK, 420, alpha=ease(t / 0.3))
        find_us(img, "Well Spent", t)
    return dict(slug="me-at-9am", product="Well Spent", tag="money journal", accent=acc,
                scenes=[(lines[i], scene(i)) for i in range(4)] + [(lines[4], end)])


def story_tbr_pile():
    acc = hexrgb("#A94E28")
    page = os.path.join(STUDIO, "previews", "well-read", "tablet", "04.jpg")
    lines = ["Books I bought this year...",
             "and the ones I actually read.",
             "Be honest!",
             "Next year? Read the pile. With Well Read."]
    hook = "my TBR pile vs what I actually read"

    def stacks(img, t, bought, read, label_alpha=1.0):
        text_block(img, hook, "italic", 74, INK, 420)
        books(img, 150, 1400, bought, acc, seed=1)
        books(img, 580, 1400, read, acc, seed=4)
        img_l = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(img_l)
        d.text((300, 1460), "bought", font=font("bold", 52), fill=MUTED + (255,), anchor="mm")
        d.text((730, 1460), "read", font=font("bold", 52), fill=MUTED + (255,), anchor="mm")
        img.alpha_composite(img_l)

    def s1(img, t, dur):
        stacks(img, t, 18 * ease(t / max(0.5, dur * 0.8)), 0, 0)

    def s2(img, t, dur):
        stacks(img, t, 18, 3 * ease(t / max(0.5, dur * 0.6)), 0)

    def s3(img, t, dur):
        stacks(img, t, 18, 3, 0)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        k = pop(t / 0.4)
        ImageDraw.Draw(lay).text((730, 1000), "be honest.", font=font("hand", int(120 * k)), fill=acc + (255,), anchor="mm")
        img.alpha_composite(lay)

    def end(img, t, dur):
        page_flash(img, page, t, acc)
        text_block(img, "next year: read the pile", "italic", 70, INK, 420, alpha=ease(t / 0.3))
        find_us(img, "Well Read", t)
    return dict(slug="tbr-pile", product="Well Read", tag="reading journal", accent=acc,
                scenes=list(zip(lines, [s1, s2, s3, end])))


STORIES = {"one-more-chapter": story_one_more_chapter, "me-at-9am": story_me_at_9am, "tbr-pile": story_tbr_pile}


# ---------------------------------------------------------------- render

# Kokoro takes its intonation from punctuation ("?", "...", "!"), so the lines
# above are written to be SPOKEN. Speed varies a little per line (a flat rate
# is what makes TTS sound read-out), and the voice is a light blend of two
# American voices so it is less of a stock preset (Luc, 12 Nov 2026: "more
# human, with intonation").
SPEEDS = [1.0, 1.06, 0.97, 0.92, 1.0]


def make_vo(lines, model_dir, outdir, blend=(("af_heart", 0.7), ("af_bella", 0.3))):
    import soundfile as sf
    from kokoro_onnx import Kokoro
    kk = Kokoro(os.path.join(model_dir, "kokoro.onnx"), os.path.join(model_dir, "voices.bin"))
    try:
        voice = sum(kk.get_voice_style(v) * w for v, w in blend)
    except Exception:  # older kokoro-onnx: no blending
        voice = blend[0][0]
    paths, durs = [], []
    for i, ln in enumerate(lines):
        speed = SPEEDS[i % len(SPEEDS)]
        s, sr = kk.create(ln, voice=voice, speed=speed, lang="en-us")
        raw, p = f"{outdir}/raw{i}.wav", f"{outdir}/vo{i}.wav"
        sf.write(raw, s, sr)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af",
                        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                        "silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                        "-ar", "44100", p], check=True)
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "csv=p=0", p], capture_output=True, text=True).stdout)
        paths.append(p)
        durs.append(d)
    return paths, durs


def render(story, out, model_dir=None, keys=None):
    lines = [ln for ln, _ in story["scenes"]]
    tmp = tempfile.mkdtemp(prefix="obp-story-")
    if model_dir:
        vo, vd = make_vo(lines, model_dir, tmp)
    else:
        vo, vd = None, [len(ln.split()) / 2.7 for ln in lines]
    durs = [max(1.3, d + 0.35) for d in vd]
    durs[-1] = max(durs[-1], 2.4)
    starts = [sum(durs[:i]) for i in range(len(durs))]
    total = sum(durs)

    if keys:
        sheet = Image.new("RGB", (len(durs) * 270, 480), "white")
        for i, (_, draw) in enumerate(story["scenes"]):
            img = Image.new("RGBA", (W, H), CREAM + (255,))
            draw(img, durs[i] * 0.85, durs[i])
            badge(img, story["product"], story["tag"], story["accent"])
            sheet.paste(img.convert("RGB").resize((270, 480)), (i * 270, 0))
        sheet.save(keys)
        return keys, round(total, 2)

    silent = os.path.join(tmp, "v.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "20", "-pix_fmt", "yuv420p", silent], stdin=subprocess.PIPE)
    n = int(round(total * FPS))
    for f in range(n):
        t = f / FPS
        i = max(k for k in range(len(starts)) if starts[k] <= t + 1e-9)
        img = Image.new("RGBA", (W, H), CREAM + (255,))
        story["scenes"][i][1](img, t - starts[i], durs[i])
        badge(img, story["product"], story["tag"], story["accent"])
        ff.stdin.write(img.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if not vo:
        os.replace(silent, out)
        return out, round(total, 2)
    inputs, filt = ["-i", silent], []
    for k, p in enumerate(vo):
        inputs += ["-i", p]
        filt.append(f"[{k + 1}:a]adelay={int(starts[k] * 1000) + 120}|{int(starts[k] * 1000) + 120}[a{k}]")
    mix = "".join(f"[a{k}]" for k in range(len(vo))) + f"amix=inputs={len(vo)}:normalize=0[a]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt + [mix]),
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-t", f"{total:.2f}", out], check=True)
    return out, round(total, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story", choices=list(STORIES) + ["all"])
    ap.add_argument("--vo", help="Kokoro model dir (kokoro.onnx + voices.bin)")
    ap.add_argument("--out")
    ap.add_argument("--outdir", default=os.path.join(ROOT, "tiktok", "videos"))
    ap.add_argument("--keys", action="store_true", help="contact sheet of one frame per scene")
    a = ap.parse_args()
    for name in (STORIES if a.story == "all" else [a.story]):
        st = STORIES[name]()
        if a.keys:
            print(render(st, None, keys=os.path.join(a.outdir, f"{name}-keys.jpg")))
        else:
            print(render(st, a.out or os.path.join(a.outdir, f"{name}.mp4"), a.vo))


if __name__ == "__main__":
    sys.exit(main())
