"""Obenpaper motion promo engine — a 6-scene product video from a per-product config.

The same engine Luc uses for the Etsy listing videos, vendored here so the
pin studio can post it as a video pin (layout "promo", since 8 Nov 2026).

Scenes: 1 hook (night, motif zoom, question)   2 reveal (cover flies in, bounce, flip)
        3 inside (3 pages slide in, handwriting + pencil star)
        4 differentiator (real page zoom, circled items, floating line symbols)
        5 value (pages · formats: tablet + A4 + US Letter)   6 sell (cover, sparkles, name pill)

Formats:
  "pin"    1000×1500, silent, ≤ 15 s — the Pinterest video pin. NO price and
           no "shop now": a pin stays up for months and the price can change.
  "etsy"   1080×1080, silent, ≤ 15 s — Etsy listing video (price pill, shop line).
  "tiktok" 1080×1920, optional Kokoro voiceover.

Configs live in pin-studio/promo/<subject>.json. Colours come from the
catalogue (§01 accent), page paths are relative to the subject's previews.
Every text field in a config is linted by `studio.py add` before a promo pin
is queued, and must only restate the subject's catalogue facts.

    python pin-studio/motion_promo.py <subject> pin|etsy|tiktok [keys] [--out PATH]

`keys` writes a contact sheet of one frame per scene instead of the video.
Without --out, videos go to listing-videos/ (git-ignored: Etsy files are
deliverables for Luc, not repo content). Needs Pillow and ffmpeg.
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
PROMO_DIR = os.path.join(STUDIO, "promo")
FONTS_DIR = os.path.join(STUDIO, "fonts")
FONT_FILES = {
    "serif": "DMSerifDisplay-Regular.ttf",
    "serif_italic": "DMSerifDisplay-Italic.ttf",
    "medium": "Poppins-Medium.ttf",
    "semibold": "Poppins-SemiBold.ttf",
    "hand": "Caveat-Variable.ttf",
}
# Text fields shown on screen — all of them are linted by the studio.
TEXT_FIELDS = ["hook", "inside_line", "sketch.handwriting", "diff.line1", "diff.line2", "sell1", "sell2"]
SCENE_DURATIONS = {
    "pin": [1.8, 2.0, 2.8, 3.0, 2.4, 2.8],     # 14.8 s
    "etsy": [1.8, 2.0, 2.8, 3.0, 2.4, 2.8],    # 14.8 s, Etsy max 15 s, no sound
    "tiktok": [2.0, 2.0, 2.8, 3.0, 2.6, 3.0],
}

FPS = 30
def clamp(x): return max(0.0, min(1.0, x))
def ease_out(t): t = clamp(t); return 1 - (1 - t) ** 3
def back_out(t, s=1.7): t = clamp(t) - 1; return t * t * ((s + 1) * t + s) + 1
def lerp(a, b, t): return a + (b - a) * t
def hx(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

FORMATS = {
    # y positions are centres; k scales pictures, ts scales type; sym_span scales scene-4 symbols
    "tiktok": dict(W=1080, H=1920, k=1.0, ts=1.0, head=330, head2=430, stage=1040, price=1390, shop=1520, brand=270,
                   sell1=380, sell2=500, sell_stage=1010, sym_span=1.0),
    "etsy":   dict(W=1080, H=1080, k=0.68, ts=0.75, head=105, head2=185, stage=630, price=915, shop=1000, brand=60,
                   sell1=110, sell2=195, sell_stage=560, sym_span=1.25),
    "pin":    dict(W=1000, H=1500, k=0.84, ts=0.86, head=240, head2=330, stage=820, price=1130, shop=1250, brand=150,
                   sell1=250, sell2=350, sell_stage=760, sym_span=1.0),
}


def get(cfg, dotted):
    v = cfg
    for part in dotted.split("."):
        v = v.get(part) if isinstance(v, dict) else None
    return v


def load_config(subject):
    """The subject's promo config, with pages resolved and the catalogue accent applied."""
    path = os.path.join(PROMO_DIR, f"{subject['key']}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"no promo config for {subject['key']} (pin-studio/promo/{subject['key']}.json)")
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    base = os.path.join(STUDIO, subject["previews"])

    def resolve(rel):
        p = os.path.join(base, rel)
        if not os.path.exists(p):
            raise FileNotFoundError(f"promo page {rel} not found in {subject['previews']}")
        return p

    P = cfg["pages"]
    cfg["pages"] = {k: (resolve(v) if isinstance(v, str) else [resolve(x) for x in v]) for k, v in P.items()}
    cfg["diff"]["page"] = resolve(cfg["diff"]["page"])
    acc = subject["accent"]
    cfg.update(accent=acc["main"], dark=acc["dark"], bg=acc["bg"])
    cfg.setdefault("name", subject["product"])
    return cfg


class Promo:
    def __init__(self, cfg, fmt):
        self.c = cfg; self.L = FORMATS[fmt]; self.fmt = fmt
        self.W, self.H = self.L["W"], self.L["H"]
        self.A, self.D, self.BG = hx(cfg["accent"]), hx(cfg["dark"]), hx(cfg["bg"])
        self.CREAM, self.INK = hx("#FDF8F2"), hx("#3B302B")
        self.NIGHT = tuple(max(0, int(v * 0.14)) for v in self.D)
        self.GLOW = (246, 236, 214)
        self._fc = {}
        k = self.L["k"]
        P = cfg["pages"]
        self.cover = self.load(P["cover_print"], int(700 * k))
        self.tab_cover = self.load(P["cover_tablet"], int(600 * k))
        self.inside = [self.load(p, int(1000 * k)) for p in P["inside"]]
        self.a4 = self.load(P["cover_print"], int(300 * k)); self.letter = self.load(P.get("second_print", P["cover_print"]), int(300 * k))
        rnd = random.Random(4)
        self.stars = [(rnd.uniform(60, self.W - 60), rnd.uniform(self.H * 0.08, self.H * 0.78), rnd.uniform(6, 16) * (k ** 0.5), rnd.uniform(0.3, 1.0)) for _ in range(26)]

    # ---------- helpers ----------
    def font(self, name, size):
        size = max(8, int(size * self.L["ts"]))
        if (name, size) not in self._fc: self._fc[(name, size)] = ImageFont.truetype(os.path.join(FONTS_DIR, FONT_FILES[name]), size)
        return self._fc[(name, size)]
    def hand_font(self, size):
        f = ImageFont.truetype(os.path.join(FONTS_DIR, FONT_FILES["hand"]), max(10, int(size)))
        try: f.set_variation_by_axes([600])
        except OSError: pass
        return f
    def load(self, path, w):
        im = Image.open(path).convert("RGB"); return im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
    def canvas(self, col): return Image.new("RGB", (self.W, self.H), col)
    def text(self, img, s, f, fill, cy, scale=1.0, alpha=1.0, cx=None):
        d0 = ImageDraw.Draw(img); l, t, r, b = d0.textbbox((0, 0), s, font=f)
        lay = Image.new("RGBA", (r - l + 20, b - t + 20), (0, 0, 0, 0))
        ImageDraw.Draw(lay).text((10 - l, 10 - t), s, font=f, fill=fill + (255,))
        if scale != 1: lay = lay.resize((max(1, int(lay.width * scale)), max(1, int(lay.height * scale))), Image.LANCZOS)
        if alpha < 1: lay.putalpha(lay.split()[3].point(lambda v: int(v * clamp(alpha))))
        x = (self.W / 2 if cx is None else cx) - lay.width / 2
        img.paste(lay, (int(x), int(cy - lay.height / 2)), lay)
    def text_width(self, s, f):
        l, _, r, _ = ImageDraw.Draw(Image.new("RGB", (4, 4))).textbbox((0, 0), s, font=f); return r - l
    def pill(self, img, s, cx, cy, size=36):
        d = ImageDraw.Draw(img); f = self.font("semibold", size); tw = d.textlength(s, font=f); h = f.size
        d.rounded_rectangle([cx - tw / 2 - 20, cy - h * 0.75, cx + tw / 2 + 20, cy + h * 0.85], radius=int(h * 0.8), fill=self.A)
        d.text((cx - tw / 2, cy - h * 0.62), s, font=f, fill=self.CREAM)
    def paste(self, img, pic, cx, cy, ang=0, scale=1.0, shadow=True):
        p = pic if scale == 1 else pic.resize((max(1, int(pic.width * scale)), max(1, int(pic.height * scale))), Image.LANCZOS)
        p = p.convert("RGBA")
        if shadow:
            sh = Image.new("RGBA", (p.width + 40, p.height + 40), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rectangle([20, 26, p.width + 20, p.height + 26], fill=(60, 40, 70, 70))
            sh = sh.filter(ImageFilter.GaussianBlur(12)).rotate(ang, expand=True, resample=Image.BICUBIC)
            img.paste(sh, (int(cx - sh.width / 2), int(cy - sh.height / 2 + 10)), sh)
        if ang: p = p.rotate(ang, expand=True, resample=Image.BICUBIC)
        img.paste(p, (int(cx - p.width / 2), int(cy - p.height / 2)), p)
    def glow(self, img, cx, cy, r, col, a=70):
        g = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (a,))
        return Image.alpha_composite(img.convert("RGBA"), g.filter(ImageFilter.GaussianBlur(r * 0.35))).convert("RGB")
    def crescent(self, img, cx, cy, r, col):
        size = int(r * 2 + 4)
        if size < 4: return
        m = Image.new("L", (size, size), 0); md = ImageDraw.Draw(m)
        md.ellipse([2, 2, size - 2, size - 2], fill=255)
        md.ellipse([2 + r * 0.45, 2 - r * 0.25, size - 2 + r * 0.45, size - 2 - r * 0.25], fill=0)
        img.paste(Image.new("RGB", (size, size), col), (int(cx - size / 2), int(cy - size / 2)), m)
    def motif(self, img, cx, cy, r, col):
        """Hero shape for scenes 1/2. 'moon' = crescent; anything else = a big sparkle."""
        if self.c.get("motif", "sparkle") == "moon": self.crescent(img, cx, cy, r, col)
        else: self.sparkle(ImageDraw.Draw(img), cx, cy, r * 1.1, col)
    @staticmethod
    def sparkle(d, cx, cy, s, col):
        d.polygon([(cx, cy - s), (cx + s * .22, cy - s * .22), (cx + s, cy), (cx + s * .22, cy + s * .22),
                   (cx, cy + s), (cx - s * .22, cy + s * .22), (cx - s, cy), (cx - s * .22, cy - s * .22)], fill=col)
    @staticmethod
    def star_pts(cx, cy, R, r):
        pts = [(cx + (R if k % 2 == 0 else r) * math.cos(-math.pi / 2 + k * math.pi / 5),
                cy + (R if k % 2 == 0 else r) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)]
        return pts + [pts[0]]

    # ---------- scenes ----------
    def s1(self, t, dur):
        L = self.L; img = self.canvas(self.NIGHT); d = ImageDraw.Draw(img)
        for x, y, s, st in self.stars:
            p = (t - st * 0.7) / 0.18
            if p > 0: self.sparkle(d, x, y, s * back_out(p, 2), self.GLOW)
        zoom = 1.0 if t < dur - 0.4 else 1 + ((t - (dur - 0.4)) / 0.4) ** 2 * 30
        r = 190 * L["k"] * back_out(clamp(t / 0.45), 1.3) * zoom
        if t > dur - 0.12: return self.canvas(self.GLOW)
        if r > 1:
            img = self.glow(img, self.W / 2, L["stage"], r * 1.6, self.GLOW, 40)
            self.motif(img, self.W / 2 - r * 0.15, L["stage"], r, self.GLOW)
        words = self.c["hook"].split(); split = self.c.get("hook_split", 3)
        shown = [w for i, w in enumerate(words) if t > 0.25 + i * 0.14]
        if shown:
            self.text(img, " ".join(shown[:split]), self.font("serif", 110), self.CREAM, L["head"] + 190 * L["k"])
            if len(shown) > split: self.text(img, " ".join(shown[split:]), self.font("serif_italic", 120), self.A, L["head"] + 330 * L["k"])
        return img

    def s2(self, t, dur):
        L = self.L; img = self.glow(self.canvas(self.BG), self.W / 2, L["stage"], 520 * L["k"], self.A, int(60 + 30 * math.sin(t * 4)))
        self.motif(img, self.W / 2 + 300 * L["k"], L["stage"] - 520 * L["k"], 90 * L["k"], self.A)
        p = clamp(t / 0.6)
        cx, cy = lerp(self.W + 400, self.W / 2, back_out(p, 1.2)), lerp(-300, L["stage"] + 40 * L["k"], back_out(p, 1.2))
        sx = 1.0 if t < dur - 0.3 else 1 - ease_out((t - (dur - 0.3)) / 0.3)
        pic = self.cover if sx >= 0.999 else self.cover.resize((max(2, int(self.cover.width * sx)), self.cover.height))
        self.paste(img, pic, cx, cy, lerp(-25, -3, ease_out(p)))
        q = (t - 0.35) / 0.3
        if q > 0:
            sc, al = lerp(1.3, 1, back_out(q, 1.5)), ease_out(q * 2)
            self.text(img, "Meet", self.font("medium", 64), self.D, L["head"] - 30 * L["ts"], sc, al)
            self.text(img, self.c["name"].upper(), self.font("serif", 130), self.INK, L["head"] + 70 * L["ts"], sc, al)
            d = ImageDraw.Draw(img)
            for k, (x, y, s) in enumerate([(0.16, -30, 26), (0.83, -60, 34), (0.88, 80, 18)]):
                self.sparkle(d, self.W * x, L["head"] + y * L["ts"], s * L["ts"] * (0.7 + 0.3 * math.sin(t * 8 + k)), self.D)
        return img

    def s3(self, t, dur):
        L, k = self.L, self.L["k"]; img = self.canvas(self.BG)
        self.text(img, self.c["inside_line"], self.font("serif", 84), self.INK, L["head"])
        sk = self.c["sketch"]  # page index in inside[], star centre and handwriting spot in SOURCE px (1200-wide page)
        ink = (70, 50, 110); s = 1000 * k / 1200
        for j, page in enumerate(self.inside):
            st = j * 0.3; p = clamp((t - st) / 0.4)
            if p <= 0: continue
            x = lerp(self.W + 600, self.W / 2 + (20 - 30 * (j % 2)) * k, ease_out(p))
            if j == sk["page"] and t > 1.0:
                page = page.copy(); pd = ImageDraw.Draw(page)
                txt = sk["handwriting"]; n = int(len(txt) * clamp((t - 1.0) / 1.0))
                hxp, hyp = sk["hand_at"]; half = txt.rfind(" ", 0, len(txt) // 2 + 1) + 1 or len(txt) // 2  # break at a space, not mid-word
                f = self.hand_font(54 * k)
                pd.text((hxp * s, hyp * s), txt[:min(n, half)], font=f, fill=ink)
                if n > half: pd.text((hxp * s, hyp * s + 60 * k), txt[half:n], font=f, fill=ink)
                sp = self.star_pts(sk["star_at"][0] * s, sk["star_at"][1] * s, 90 * k, 38 * k)
                seg = clamp((t - 1.1) / 1.0) * (len(sp) - 1)
                for i in range(int(seg)): pd.line([sp[i], sp[i + 1]], fill=ink, width=max(2, int(7 * k)))
            self.paste(img, page, x, L["stage"] + (j - 1) * 25 * k)
        if 1.1 < t < 2.1:
            pg = self.inside[sk["page"]]
            sp = self.star_pts(sk["star_at"][0] * s, sk["star_at"][1] * s, 90 * k, 38 * k)
            seg = min(len(sp) - 1.001, clamp((t - 1.1) / 1.0) * (len(sp) - 1)); i = int(seg); fr = seg - i
            tx = lerp(sp[i][0], sp[i + 1][0], fr) + self.W / 2 - pg.width / 2
            ty = lerp(sp[i][1], sp[i + 1][1], fr) + L["stage"] + (sk["page"] - 1) * 25 * k - pg.height / 2
            d = ImageDraw.Draw(img)
            d.line([tx, ty, tx + 260 * k, ty - 380 * k], fill=(60, 60, 66), width=max(6, int(24 * k)))
            d.line([tx, ty, tx + 22 * k, ty - 32 * k], fill=(205, 190, 160), width=max(6, int(24 * k)))
        if t > dur - 0.25:
            q = ease_out((t - (dur - 0.25)) / 0.25)
            sh = self.canvas(self.BG); sh.paste(img, (int(-q * self.W * 0.7), 0))
            img = sh.filter(ImageFilter.BoxBlur(int(2 + q * 10)))
        return img

    def sym(self, d, kind, cx, cy, s, col):
        w = max(3, int(6 * self.L["ts"]))
        if kind == "moon": self.crescent(d._image, cx, cy, s, col)
        elif kind == "star": d.line(self.star_pts(cx, cy, s, s * 0.42), fill=col, width=w)
        elif kind == "cloud":
            for dx, dy, r in [(-s * .5, 0, s * .45), (0, -s * .25, s * .55), (s * .5, 0, s * .45)]:
                d.ellipse([cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r], outline=col, width=w)
        elif kind == "door":
            d.rounded_rectangle([cx - s * .5, cy - s, cx + s * .5, cy + s], radius=int(s * .5), outline=col, width=w)
        elif kind == "wave":
            d.line([(cx - s + i * 2 * s / 30, cy + math.sin(i / 30 * 3 * math.pi) * s * .3) for i in range(31)], fill=col, width=w)
        elif kind == "key":
            d.ellipse([cx - s, cy - s * .35, cx - s * .3, cy + s * .35], outline=col, width=w); d.line([cx - s * .3, cy, cx + s, cy], fill=col, width=w)
        elif kind == "heart":
            d.line([(cx + 16 * math.sin(a) ** 3 * s / 17, cy - (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) * s / 17)
                    for a in [i / 40 * 2 * math.pi for i in range(41)]], fill=col, width=w)
        elif kind == "dot": d.ellipse([cx - s * .3, cy - s * .3, cx + s * .3, cy + s * .3], outline=col, width=w)

    def s4(self, t, dur):
        L, k = self.L, self.L["k"]; img = self.canvas(self.BG); df = self.c["diff"]
        self.text(img, df["line1"], self.font("serif", 84), self.INK, L["head"])
        self.text(img, df["line2"], self.font("serif_italic", 92), self.D, L["head2"])
        p = clamp((t - 0.5) / 0.5)
        x0, y0, x1, y1 = df["crop"]
        zw = int(960 * k); sc = zw / (x1 - x0)
        if p > 0:
            z = Image.open(df["page"]).convert("RGB").crop((x0, y0, x1, y1)).resize((zw, int((y1 - y0) * sc)), Image.LANCZOS)
            cy = lerp(L["stage"] + 280 * k, L["stage"], back_out(p, 1.2))
            self.paste(img, z, self.W / 2, cy, 0, lerp(0.85, 1, ease_out(p)))
            zx0, zy0 = self.W / 2 - zw / 2, L["stage"] - z.height / 2
            d = ImageDraw.Draw(img)
            for j, (a0, b0, a1, b1) in enumerate(df["circle"]):
                q = clamp((t - 1.3 - j * 0.4) / 0.4)
                if q > 0:
                    d.arc([zx0 + (a0 - x0 - 10) * sc, zy0 + (b0 - y0 - 8) * sc, zx0 + (a1 - x0 + 10) * sc, zy0 + (b1 - y0 + 8) * sc],
                          start=-90, end=-90 + 380 * q, fill=self.D, width=max(4, int(8 * k)))
        d = ImageDraw.Draw(img)
        spots = [(0.17, -0.22), (0.83, -0.21), (0.16, 0.2), (0.83, 0.2), (0.37, 0.24), (0.64, 0.24)]
        for j, kind in enumerate(df.get("symbols", ["star", "heart", "dot", "cloud", "wave", "key"])[:6]):
            q = clamp((t - j * 0.12) / 0.5)
            if q > 0:
                fx, fy = spots[j]
                yy = L["stage"] + fy * self.H * L["sym_span"] + math.sin(t * 2 + j) * 14 * k + lerp(80, 0, ease_out(q)) * k
                self.sym(d, kind, self.W * fx, yy, 60 * k ** 0.6 * back_out(q, 1.6), self.A)
        if t > dur - 0.15: img = Image.blend(img, self.canvas(self.CREAM), clamp((t - (dur - 0.15)) / 0.15))
        return img

    def s5(self, t, dur):
        L, k = self.L, self.L["k"]; img = self.canvas(self.CREAM)
        self.text(img, f"{self.c['pages_count']} pages · 3 formats", self.font("serif", 96), self.INK, L["head"])
        p = clamp(t / 0.5); tx = lerp(-500, self.W * 0.31, back_out(p, 1.1))
        bez = Image.new("RGB", (self.tab_cover.width + int(36 * k), self.tab_cover.height + int(36 * k)), (40, 38, 44))
        bez.paste(self.tab_cover, (int(18 * k), int(18 * k)))
        tab = bez.rotate(90, expand=True); tab = tab.resize((int(tab.width * .78), int(tab.height * .78)), Image.LANCZOS)
        self.paste(img, tab, tx, L["stage"])
        for j, (pg, lab) in enumerate([(self.a4, "A4"), (self.letter, "US Letter")]):
            q = clamp((t - 0.35 - j * 0.2) / 0.5)
            if q <= 0: continue
            x = lerp(self.W + 300, self.W * 0.76, back_out(q, 1.1)); y = L["stage"] - 200 * k + j * 470 * k
            self.paste(img, pg, x, y); self.pill(img, lab, x, y + pg.height / 2 + 20 * k, 32)
        if t > 0.5: self.pill(img, "Tablet", tx, L["stage"] + tab.height / 2 + 30 * k, 32)
        if t > dur - 0.3:
            q = ease_out((t - (dur - 0.3)) / 0.3); s = lerp(1, 0.6, q)
            small = img.resize((int(self.W * s), int(self.H * s)), Image.LANCZOS)
            img = self.canvas(self.BG); img.paste(small, (int((self.W - small.width) / 2), int((self.H - small.height) / 2)))
        return img

    def s6(self, t, dur):
        L, k = self.L, self.L["k"]
        img = self.glow(self.canvas(self.BG), self.W / 2, L["sell_stage"], 460 * k, self.A, 70)
        self.text(img, self.c["sell1"], self.font("serif", 104), self.INK, L["sell1"], lerp(1.2, 1, back_out(clamp(t / .3), 1.4)))
        self.text(img, self.c["sell2"], self.font("serif_italic", 104), self.D, L["sell2"], lerp(1.2, 1, back_out(clamp((t - .12) / .3), 1.4)))
        p = clamp(t / 0.5)
        self.paste(img, self.cover, self.W / 2, lerp(L["sell_stage"] + 400 * k, L["sell_stage"], back_out(p, 1.2)), lerp(6, 0, ease_out(p)), 0.68)
        d = ImageDraw.Draw(img)
        for j in range(9):
            a = j / 9 * 2 * math.pi + t * 0.6
            self.sparkle(d, self.W / 2 + math.cos(a) * 360 * k, L["sell_stage"] + math.sin(a) * 400 * k,
                         (16 + 10 * max(0, math.sin(t * 6 + j * 1.7))) * k ** 0.5, self.D if j % 2 else self.A)
        q = (t - 0.7) / 0.4
        if q > 0:
            # A pin never shows a price: it stays up for months and prices change.
            txt = self.c["name"].upper() if self.fmt == "pin" else f"{self.c['name'].upper()} · {self.c['price']}"
            s = back_out(q, 2.0); f = self.font("semibold", 52)
            tw = d.textlength(txt, font=f); bw, bh = (tw + 80 * L["ts"]) * s, 104 * L["ts"] * s
            d.rounded_rectangle([self.W / 2 - bw / 2, L["price"] - bh / 2, self.W / 2 + bw / 2, L["price"] + bh / 2], radius=int(52 * L["ts"] * s), fill=self.D)
            if s > 0.6: self.text(img, txt, self.font("semibold", int(52 * min(s, 1.1))), self.CREAM, L["price"])
        r = (t - 1.2) / 0.4
        if r > 0:
            line = "obenpaper.com" if self.fmt == "pin" else self.c.get("shop_line", "SHOP NOW — OBENPAPER")
            self.text(img, line, self.font("semibold", 44), self.INK, L["shop"], 1, ease_out(r * 2))
            if self.fmt == "tiktok": self.text(img, "obenpaper", self.font("serif", 60), self.D, L["brand"], 1, ease_out(r * 2))
        return img

    # ---------- render ----------
    def scenes(self):
        return [self.s1, self.s2, self.s3, self.s4, self.s5, self.s6]

    def grain(self, img):
        if not hasattr(self, "_g"):
            rnd = random.Random(7); g = Image.new("L", (self.W // 2, self.H // 2))
            g.putdata([128 + int(rnd.gauss(0, 22)) for _ in range(self.W // 2 * self.H // 2)])
            self._g = Image.merge("RGB", [g.resize((self.W, self.H), Image.BILINEAR)] * 3)
        return Image.blend(img, self._g, 0.03)

    def check_fits(self):
        """Refuse a config whose on-screen lines run off the frame (margin 6 %)."""
        limit = self.W * 0.88
        lines = [("hook", " ".join(self.c["hook"].split()[:self.c.get("hook_split", 3)]), "serif", 110),
                 ("hook", " ".join(self.c["hook"].split()[self.c.get("hook_split", 3):]), "serif_italic", 120),
                 ("name", self.c["name"].upper(), "serif", 130),
                 ("inside_line", self.c["inside_line"], "serif", 84),
                 ("diff.line1", self.c["diff"]["line1"], "serif", 84),
                 ("diff.line2", self.c["diff"]["line2"], "serif_italic", 92),
                 ("pages line", f"{self.c['pages_count']} pages · 3 formats", "serif", 96),
                 ("sell1", self.c["sell1"], "serif", 104), ("sell2", self.c["sell2"], "serif_italic", 104)]
        too_wide = [f for f, s, face, size in lines if self.text_width(s, self.font(face, size)) > limit]
        if too_wide:
            raise ValueError(f"promo text too wide for {self.fmt}: {', '.join(too_wide)} — shorten it")

    def frame(self, scene, t, durs):
        return self.grain(self.scenes()[scene](t, durs[scene]))

    def render(self, out, durs, vo=None, cover=None):
        self.check_fits()
        tmpdir = tempfile.mkdtemp(prefix="obp-promo-"); parts = []
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is not installed — promo videos need it")
        try:
            for i, (fn, dur) in enumerate(zip(self.scenes(), durs)):
                part = f"{tmpdir}/s{i}.mp4"
                p = subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.W}x{self.H}", "-r", str(FPS),
                                      "-i", "-", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", part], stdin=subprocess.PIPE)
                for f in range(int(round(dur * FPS))): p.stdin.write(self.grain(fn(f / FPS, dur)).tobytes())
                p.stdin.close()
                if p.wait() != 0: raise RuntimeError(f"ffmpeg failed on scene {i + 1}")
                parts.append(part)
            with open(f"{tmpdir}/list.txt", "w") as fh:
                fh.write("".join(f"file '{x}'\n" for x in parts))
            silent = f"{tmpdir}/v.mp4"
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{tmpdir}/list.txt", "-c", "copy",
                            "-movflags", "+faststart", silent], check=True)
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            if not vo:
                shutil.move(silent, out)
            else:
                starts, acc = [], 0.0
                for d_ in durs: starts.append(acc + 0.1); acc += d_
                ins, flt = [], []
                for i, w in enumerate(vo):
                    ins += ["-i", w]; ms = int(starts[i] * 1000); flt.append(f"[{i+1}:a]adelay={ms}|{ms},volume=1.3[a{i}]")
                mix = ";".join(flt) + ";" + "".join(f"[a{i}]" for i in range(len(vo))) + f"amix=inputs={len(vo)}:normalize=0,alimiter=limit=0.89,apad[a]"
                subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", silent, *ins, "-filter_complex", mix, "-map", "0:v", "-map", "[a]",
                                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", out], check=True)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        if cover:
            # The cover is the finished sell scene: product, name and obenpaper.com.
            self.frame(5, durs[5] - 1 / FPS, durs).save(cover)
        return out

    def keys(self, out, durs):
        self.check_fits()
        times = [0.75, 0.55, 0.7, 0.8, 0.6, 0.7]
        th = (240, int(240 * self.H / self.W))
        sheet = Image.new("RGB", (6 * 250, th[1] + 10), "white")
        for i, d_ in enumerate(durs):
            sheet.paste(self.frame(i, d_ * times[i], durs).resize(th), (i * 250, 0))
        sheet.save(out)
        return out


def render_pin_promo(subject, mp4_out, png_out):
    """A promo video pin: 1000×1500 silent MP4 and its PNG cover."""
    pr = Promo(load_config(subject), "pin")
    return pr.render(mp4_out, SCENE_DURATIONS["pin"], cover=png_out)


def make_vo(lines, outdir, model_dir, voice="af_heart", speed=1.25):
    """Kokoro TTS per line, silence-trimmed. Returns (wav paths, durations)."""
    import soundfile as sf
    from kokoro_onnx import Kokoro
    kk = Kokoro(model_dir + "/kokoro.onnx", model_dir + "/voices.bin"); os.makedirs(outdir, exist_ok=True)
    paths, durs = [], []
    for i, l in enumerate(lines):
        s, sr = kk.create(l, voice=voice, speed=speed, lang="en-us"); raw = f"{outdir}/raw{i}.wav"; sf.write(raw, s, sr)
        p = f"{outdir}/vo{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af",
                        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                        "-ar", "44100", p], check=True)
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout)
        paths.append(p); durs.append(d)
    return paths, durs


def main(argv):
    sys.path.insert(0, STUDIO)
    from render_tile import load_catalogue
    args = [a for a in argv if not a.startswith("--out")]
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--out=")), None)
    if len(args) < 2 or args[1] not in FORMATS:
        sys.exit(__doc__)
    subject = load_catalogue().get(args[0])
    if not subject:
        sys.exit(f"unknown subject '{args[0]}'")
    fmt = args[1]
    cfg = load_config(subject)
    pr = Promo(cfg, fmt)
    durs, vo = SCENE_DURATIONS[fmt], None
    if fmt == "tiktok" and cfg.get("voiceover") and cfg.get("kokoro_dir"):
        vo, vd = make_vo(cfg["voiceover"], tempfile.mkdtemp(prefix="obp-vo-"), cfg["kokoro_dir"])
        durs = [max(m, d + 0.35) for m, d in zip(durs, vd)]
    if fmt != "tiktok":
        assert sum(durs) <= 15.0
    stem = f"Obenpaper-{cfg['name'].replace(' ', '')}-{fmt}"
    folder = os.path.join(ROOT, "listing-videos")
    if args[2:3] == ["keys"]:
        path = out or os.path.join(folder, f"{stem}-keys.jpg")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        print(pr.keys(path, durs))
    else:
        path = out or os.path.join(folder, f"{stem}-video.mp4")
        print(pr.render(path, durs, vo), round(sum(durs), 2))


if __name__ == "__main__":
    main(sys.argv[1:])
