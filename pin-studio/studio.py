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

`add` fills product, category (board), link and guardrail from the
catalogue, gives each pin an id and an image file, renders the tile, then
validates the WHOLE queue with the publisher's own rules. If anything fails,
nothing is written and the tile files it rendered are removed.

House rules enforced here on top of the publisher's:
  - a subject is pinned at most once every SUBJECT_GAP_DAYS days
  - a tile never reuses the exact page(s) of an earlier tile for that subject
"""

import json
import os
import sys
from datetime import datetime, timedelta

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
API = os.path.join(ROOT, "pinterest-api")
sys.path.insert(0, API)
sys.path.insert(0, STUDIO)

from obenpaper_rules import TIMEZONE  # noqa: E402
from render_tile import PINS_DIR, load_catalogue, render  # noqa: E402
from validate_queue import (MAP_PATH, PINS_PATH, POSTED_PATH, load_json,  # noqa: E402
                            parse_when, validate)

HORIZON_DAYS = 14
CADENCE_DAYS = 2           # one pin every two days (1–2 day spacing rule)
POST_TIME = "19:00:00"     # Zurich, evening
SUBJECT_GAP_DAYS = 6


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
    print(f"\nPages already used ({len(used)}):")
    for u in used:
        print(f"  {u}")


def open_slots():
    pins, _ = load_state()
    dated = sorted(parse_when(p["scheduled_at"]) for p in pins)
    start = now() + timedelta(hours=12)
    last = dated[-1] if dated else None
    day = (last + timedelta(days=CADENCE_DAYS)).date() if last and last > start else start.date()
    end = (now() + timedelta(days=HORIZON_DAYS)).date()
    slots = []
    while day <= end:
        slots.append(f"{day.isoformat()}T{POST_TIME}")
        day += timedelta(days=CADENCE_DAYS)
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
            "link": subject["link"],
            "image_file": f"{pid.lower()}.png",
            "image_url": "",
            "title": d["title"].strip(),
            "description": " ".join(d["description"].split()),
            "alt_text": " ".join(d["alt_text"].split()),
            "scheduled_at": d["scheduled_at"],
            "tile": d["tile"],
            "made_by": "claude",
        }
        new.append(pin)

    # House rules: subject spacing and no reused pages.
    everything = pins + new
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
                render(pin, catalogue[pin["subject"]], out)
                rendered.append(out)
            except (ValueError, FileNotFoundError) as exc:
                problems.append(f"{pin['id']}: tile — {exc}")

    if not problems:
        errors, warnings, _ = validate(everything, board_map, set(posted), require_boards=False)
        problems.extend(errors)
        for w in warnings:
            if "not mapped yet" not in w:
                print(f"WARNING  {w}")

    if problems:
        for out in rendered:
            os.remove(out)
        for p in problems:
            print(f"ERROR    {p}")
        print("\nNothing written. Fix the drafts and run again.")
        return 1

    with open(PINS_PATH, "w", encoding="utf-8") as fh:
        json.dump(everything, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    for pin in new:
        print(f"added {pin['id']}  →  pins/{pin['image_file']}")
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
