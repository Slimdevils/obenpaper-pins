"""The weekly pin agent's tool. Run from the repo root.

    python pin-studio/studio.py status            # what is queued, posted, and when each subject last ran
    python pin-studio/studio.py slots             # the open dates to fill (next 14 days)
    python pin-studio/studio.py add batch.json    # add drafted pins: fill, render, validate, write

A batch file is a JSON list of drafts. The agent writes ONLY the creative
part; everything that must not be guessed comes from catalogue.json:

    {
      "subject": "student-planner",              # key in catalogue.json
      "scheduled_at": "2026-10-03T19:00:00",     # one of the dates from `slots`
      "title": "...", "description": "...", "alt_text": "...",
      "tile": {"layout": "pages", "kicker": "...", "headline": "...",
               "subline": "...", "pages": ["print/03.jpg"]}
    }

A tile with "layout": "video" (3–5 pages of one edition) becomes a video
pin: an 11–13 s MP4 flip-through plus its PNG cover, both in pins/. It needs
Node and `npm ci --prefix pin-studio/video` (see video_spec.py).

A tile with "layout": "promo" (no other tile fields) becomes the product's
motion promo — the same 6-scene video as its Etsy listing video, rendered at
1000×1500 without price (motion_promo.py, config in pin-studio/promo/). Only
for subjects with a promo config, once per subject, ever.

`add` fills product, category (board), link and guardrail from the
catalogue, gives each pin an id and an image file, renders the tile, then
validates the WHOLE queue with the publisher's own rules. If anything fails,
nothing is written and the tile files it rendered are removed.

House rules enforced here on top of the publisher's:
  - a subject is pinned at most once every SUBJECT_GAP_DAYS days
  - a tile never reuses the exact page(s) of an earlier tile for that subject
  - never two video pins (video or promo) in a row
  - a promo pin: config exists, posted once per subject, every on-screen line
    passes the guardrail lint and shows no price
"""

import contextlib
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
API = os.path.join(ROOT, "pinterest-api")
sys.path.insert(0, API)
sys.path.insert(0, STUDIO)

from obenpaper_rules import MIN_HOURS_APART, TIMEZONE  # noqa: E402
from render_tile import PINS_DIR, load_catalogue, render  # noqa: E402
from validate_queue import (MAP_PATH, PINS_PATH, POSTED_PATH, load_json,  # noqa: E402
                            parse_when, validate)

HORIZON_DAYS = 7           # 8 Nov 2026 audit: weekly run fills one week ahead
POST_TIMES = ["12:00:00", "19:00:00"]   # Zurich — two pins a day (audit, 8 Nov 2026)
SUBJECT_GAP_DAYS = 6
VIDEO_LAYOUTS = {"video", "promo"}
PRICE = re.compile(r"[€$£]|\bCHF\b|\bEUR\b|\bUSD\b|\d+[.,]\d{2}\b|\bfree\b", re.I)


def is_video(pin):
    return pin.get("media") == "video" or pin.get("tile", {}).get("layout") in VIDEO_LAYOUTS


def promo_problems(pin, subject):
    """Why a promo pin cannot be queued for this subject ([] if it can)."""
    from guardrail_lint import lint
    from motion_promo import TEXT_FIELDS, get, load_config
    try:
        cfg = load_config(subject)
    except (FileNotFoundError, KeyError) as exc:
        return [f"{pin['id']}: promo — {exc}"]
    if subject.get("kind") != "product":
        return [f"{pin['id']}: promo videos are for products only"]
    problems = []
    texts = [get(cfg, f) or "" for f in TEXT_FIELDS]
    for t in texts:
        if PRICE.search(t):
            problems.append(f"{pin['id']}: promo text shows a price or 'free' — '{t}'")
    with contextlib.redirect_stdout(io.StringIO()):
        clean = lint(subject["guardrail"], "\n".join(texts))
    if not clean:
        problems.append(f"{pin['id']}: promo text fails the {subject['guardrail']} guardrail lint "
                        f"(python pinterest-api/guardrail_lint.py {subject['guardrail']} -)")
    facts = " ".join(subject.get("facts", []))
    if f"{cfg.get('pages_count')} pages" not in facts:
        problems.append(f"{pin['id']}: promo says {cfg.get('pages_count')} pages — not in the catalogue facts")
    if not all(f in facts for f in ("tablet", "A4", "US Letter")):
        problems.append(f"{pin['id']}: promo shows tablet + A4 + US Letter — not all in the catalogue facts")
    return problems


def now():
    return datetime.now(TIMEZONE)


def load_state():
    pins = load_json(PINS_PATH, [])
    posted = {e["pin"]: e for e in load_json(POSTED_PATH, [])}
    return pins, posted


def status():
    pins, posted = load_state()
    last_by_subject = {}
    for pin in pins:
        when = parse_when(pin["scheduled_at"])
        key = pin.get("subject") or pin.get("product")
        last_by_subject[key] = max(last_by_subject.get(key, when), when)
    upcoming = [p for p in pins if p["id"] not in posted and parse_when(p["scheduled_at"]) >= now()]
    print(f"{len(pins)} pins in the queue · {len(posted)} posted · {len(upcoming)} upcoming\n")
    print("Upcoming:")
    for p in sorted(upcoming, key=lambda p: p["scheduled_at"]):
        print(f"  {p['scheduled_at'][:16]}  {p['id']:<38} {p['product']}")
    print("\nLast scheduled per subject (catalogue order):")
    for key in load_catalogue():
        when = last_by_subject.get(key)
        print(f"  {key:<24} {when.strftime('%Y-%m-%d') if when else 'never'}")
    used = sorted({f"{p.get('subject')}:{'+'.join(p.get('tile', {}).get('pages', []))}"
                   for p in pins if p.get("tile", {}).get("pages")})
    promos = sorted(p["subject"] for p in pins if p.get("tile", {}).get("layout") == "promo")
    from motion_promo import PROMO_DIR
    ready = sorted(f[:-5] for f in os.listdir(PROMO_DIR) if f.endswith(".json"))
    print(f"\nPromo videos — config ready: {', '.join(ready) or 'none'} · already pinned: {', '.join(promos) or 'none'}")
    print(f"\nPages already used ({len(used)}):")
    for u in used:
        print(f"  {u}")


def open_slots():
    """Every free slot in the next HORIZON_DAYS: POST_TIMES each day, skipping any
    time within MIN_HOURS_APART of a pin already queued (gaps get filled too)."""
    pins, _ = load_state()
    taken = [parse_when(p["scheduled_at"]).replace(tzinfo=None) for p in pins]
    start = (now() + timedelta(hours=12)).replace(tzinfo=None)
    day = start.date()
    end = (now() + timedelta(days=HORIZON_DAYS)).date()
    slots = []
    while day <= end:
        for t in POST_TIMES:
            slot = f"{day.isoformat()}T{t}"
            when = parse_when(slot).replace(tzinfo=None)
            if when <= start:
                continue
            if any(abs((when - x).total_seconds()) < MIN_HOURS_APART * 3600 for x in taken):
                continue
            slots.append(slot)
        day += timedelta(days=1)
    return slots


def slots():
    found = open_slots()
    if not found:
        print(f"Queue already covers the next {HORIZON_DAYS} days. Nothing to add.")
    for s in found:
        print(s)


def add(batch_path):
    catalogue = load_catalogue()
    with open(batch_path, "r", encoding="utf-8") as fh:
        drafts = json.load(fh)
    pins, posted = load_state()
    board_map = load_json(MAP_PATH, {})

    new, rendered, problems = [], [], []
    existing_ids = {p["id"] for p in pins}
    for i, d in enumerate(drafts, 1):
        subject = catalogue.get(d.get("subject"))
        if not subject:
            problems.append(f"draft {i}: unknown subject '{d.get('subject')}'")
            continue
        day = d["scheduled_at"][:10]
        pid = f"A-{day}-{subject['key']}"
        if pid in existing_ids:
            problems.append(f"draft {i}: {pid} already exists")
            continue
        pin = {
            "id": pid,
            "subject": subject["key"],
            "product": subject["product"],
            "category": subject["board"],
            "guardrail": subject["guardrail"],
            "link": (subject.get("etsy_link") if d.get("link_to") == "etsy" else subject["link"]) or subject["link"],
            "image_file": f"{pid.lower()}.png",
            "image_url": "",
            **({"media": "video", "video_file": f"{pid.lower()}.mp4"}
               if d.get("tile", {}).get("layout") in VIDEO_LAYOUTS else {}),
            "title": d["title"].strip(),
            "description": " ".join(d["description"].split()),
            "alt_text": " ".join(d["alt_text"].split()),
            "scheduled_at": d["scheduled_at"],
            "tile": d["tile"],
            "made_by": "claude",
        }
        new.append(pin)

    # House rules: subject spacing, no reused pages, no two videos in a row, promos.
    everything = pins + new
    ordered = sorted(everything, key=lambda p: p["scheduled_at"])
    for pin in new:
        i = ordered.index(pin)
        for other in ordered[max(0, i - 1):i] + ordered[i + 1:i + 2]:
            if is_video(pin) and is_video(other):
                problems.append(f"{pin['id']}: video right next to video {other['id']} — make one an image pin")
        if pin["tile"].get("layout") == "promo":
            problems.extend(promo_problems(pin, catalogue[pin["subject"]]))
            for other in everything:
                if other is not pin and other.get("subject") == pin["subject"] \
                        and other.get("tile", {}).get("layout") == "promo":
                    problems.append(f"{pin['id']}: {pin['subject']} already has its promo pin ({other['id']}) — once per product")
    for pin in new:
        when = parse_when(pin["scheduled_at"])
        for other in everything:
            if other is pin or other.get("subject") != pin["subject"]:
                continue
            gap = abs((parse_when(other["scheduled_at"]) - when).days)
            if gap < SUBJECT_GAP_DAYS:
                problems.append(f"{pin['id']}: same subject as {other['id']} only {gap} day(s) apart "
                                f"(min {SUBJECT_GAP_DAYS})")
            pages = pin["tile"].get("pages")
            if pages and pages == other.get("tile", {}).get("pages"):
                problems.append(f"{pin['id']}: reuses the exact page(s) of {other['id']} — pick others")

    if not problems:
        for pin in new:
            out = os.path.join(PINS_DIR, pin["image_file"])
            try:
                if pin["tile"].get("layout") == "promo":
                    from motion_promo import render_pin_promo  # Pillow + ffmpeg, no Node
                    video = os.path.join(PINS_DIR, pin["video_file"])
                    rendered.append(video)
                    rendered.append(out)
                    render_pin_promo(catalogue[pin["subject"]], video, out)
                elif pin.get("media") == "video":
                    from video_spec import render_pin_video  # needs Node; image pins never import it
                    video = os.path.join(PINS_DIR, pin["video_file"])
                    rendered.append(video)
                    rendered.append(out)
                    render_pin_video(pin, catalogue[pin["subject"]], video, out)
                else:
                    render(pin, catalogue[pin["subject"]], out)
                    rendered.append(out)
            except (ValueError, FileNotFoundError, RuntimeError) as exc:
                problems.append(f"{pin['id']}: tile — {exc}")

    if not problems:
        errors, warnings, _ = validate(everything, board_map, set(posted), require_boards=False)
        problems.extend(errors)
        for w in warnings:
            if "not mapped yet" not in w:
                print(f"WARNING  {w}")

    if problems:
        for out in rendered:
            if os.path.exists(out):
                os.remove(out)
        for p in problems:
            print(f"ERROR    {p}")
        print("\nNothing written. Fix the drafts and run again.")
        return 1

    with open(PINS_PATH, "w", encoding="utf-8") as fh:
        json.dump(everything, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    for pin in new:
        extra = f" + pins/{pin['video_file']}" if pin.get("video_file") else ""
        print(f"added {pin['id']}  →  pins/{pin['image_file']}{extra}")
    print(f"\n{len(new)} pin(s) added. Look at every tile before committing.")
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"status", "slots", "add"}:
        sys.exit(__doc__)
    if sys.argv[1] == "status":
        status()
    elif sys.argv[1] == "slots":
        slots()
    else:
        if len(sys.argv) != 3:
            sys.exit("usage: studio.py add batch.json")
        sys.exit(add(sys.argv[2]))


if __name__ == "__main__":
    main()
