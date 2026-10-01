"""Publish due pins to Pinterest via POST /v5/pins.

Run:  python pinterest_publish.py --dry-run     (shows payloads, sends nothing)
      python pinterest_publish.py               (publishes what is due)
      python pinterest_publish.py --pin SP-1    (one pin now, ignoring its date)

In normal use this runs every hour from GitHub Actions (see
.github/workflows/publish-pins.yml); running it by hand is for dry-runs.

Order of operations, every run:
  1. validate_queue.validate() — any error and NOTHING publishes.
  2. Pick pins whose scheduled_at (Zurich time) has passed, that are not in
     posted_ids.json and not missed (over 24 h late — never posted late).
  3. Cap at max_posts_per_run (1 in the cloud, so a backlog cannot burst).
  4. Fill image_url from pins/<image_file> in this repo if it is empty, and
     check Pinterest could fetch it anonymously.
  5. POST, then record the pin in posted_ids.json immediately.

Safe to re-run: posted pin IDs are recorded and skipped. No token or secret
is ever printed.
"""

import argparse
import json
import os
import sys
from datetime import datetime

import requests

from obenpaper_rules import BOARDS, LIMITS, TIMEZONE
from pinterest_common import API_BASE, HERE, auth_headers, load_config
from validate_queue import POSTED_PATH, load_json, load_queue, parse_when, validate

PINS_ENDPOINT = f"{API_BASE}/pins"
REPO_PINS_DIR = os.path.join(os.path.dirname(HERE), "pins")


def record_posted(entry):
    posted = load_json(POSTED_PATH, [])
    posted.append(entry)
    with open(POSTED_PATH, "w", encoding="utf-8") as fh:
        json.dump(posted, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def raw_url(cfg, filename):
    return (
        f"https://raw.githubusercontent.com/{cfg['github_owner']}/"
        f"{cfg['github_repo']}/{cfg['github_branch']}/pins/{filename}"
    )


def resolve_image_url(pin, cfg):
    """Return (url, problem). Uses the committed pins/<image_file> if needed."""
    if pin.get("image_url"):
        return pin["image_url"], None
    filename = pin.get("image_file")
    if filename and os.path.exists(os.path.join(REPO_PINS_DIR, filename)):
        return raw_url(cfg, filename), None
    return None, (f"image_url is empty and pins/{filename} is not committed — "
                  "commit the PNG to pins/ or run pinterest_upload_images.py")


def image_reachable(url):
    """Anonymous fetch — exactly what Pinterest's servers will do."""
    try:
        resp = requests.get(url, timeout=30)
    except requests.RequestException:
        return False
    return resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("image/")


def build_payload(pin, board_map, image_url):
    payload = {
        "board_id": board_map[pin["category"]],
        "title": pin["title"],
        "description": pin["description"],
        "alt_text": pin["alt_text"],
        "media_source": {"source_type": "image_url", "url": image_url},
    }
    link = pin.get("link", "").strip()
    if link:
        payload["link"] = link
    for field, limit in LIMITS.items():
        assert len(payload[field]) <= limit  # validate() already refused longer
    return payload


def publish(pin, payload, headers, dry_run):
    print(f"\n--- {pin['id']} · {pin['product']} → {BOARDS.get(pin['category'], pin['category'])} ---")
    print(f"POST {PINS_ENDPOINT}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if dry_run:
        print("DRY RUN — not sent.")
        return True

    resp = requests.post(PINS_ENDPOINT, headers=headers, json=payload, timeout=60)
    print(f"HTTP {resp.status_code}")
    try:
        body = resp.json()
        print(json.dumps(body, indent=2, ensure_ascii=False))
    except ValueError:
        body = {}
        print(resp.text)

    if resp.status_code not in (200, 201):
        print(f"FAILED — {pin['id']} not recorded as posted; it will be retried next run "
              "while it is within its 24 h window.")
        return False

    record_posted({
        "pin": pin["id"],
        "product": pin["product"],
        "link": payload.get("link", ""),
        "pinterest_pin_id": body.get("id"),
        "scheduled_at": pin["scheduled_at"],
        "posted_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
    })
    print(f"OK — Pinterest pin {body.get('id')} recorded in posted_ids.json")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show payloads, send nothing.")
    parser.add_argument("--pin", help="Publish one pin by its id, ignoring its date.")
    args = parser.parse_args()

    cfg = load_config()
    pins, board_map, posted_ids = load_queue()
    if not pins:
        print("Queue is empty. Nothing to do.")
        return 0

    now = datetime.now(TIMEZONE)
    errors, warnings, missed = validate(pins, board_map, posted_ids, now)
    for line in warnings:
        print(f"WARNING  {line}")
    if errors:
        for line in errors:
            print(f"ERROR    {line}")
        print("\nQueue has errors — nothing published. Fix pins_export.json first.")
        return 1

    if args.pin:
        queue = [p for p in pins if p.get("id") == args.pin]
        if not queue:
            sys.exit(f"No pin with id '{args.pin}' in pins_export.json")
        if args.pin in posted_ids:
            sys.exit(f"{args.pin} is already in posted_ids.json — refusing to post it twice.")
    else:
        queue = sorted(
            (p for p in pins
             if p["id"] not in posted_ids and p["id"] not in missed
             and parse_when(p["scheduled_at"]) <= now),
            key=lambda p: parse_when(p["scheduled_at"]),
        )

    if not queue:
        print("Nothing due.")
        return 0

    cap = int(cfg.get("max_posts_per_run", 1))
    if len(queue) > cap:
        print(f"{len(queue)} pins due; posting {cap} this run (max_posts_per_run).")
        queue = queue[:cap]

    headers = None if args.dry_run else auth_headers(cfg)
    failed = 0
    for pin in queue:
        image_url, problem = resolve_image_url(pin, cfg)
        if problem:
            print(f"\nSKIP {pin['id']} — {problem}")
            failed += 1
            continue
        if not args.dry_run and not image_reachable(image_url):
            print(f"\nSKIP {pin['id']} — image not publicly fetchable: {image_url}")
            failed += 1
            continue
        if not publish(pin, build_payload(pin, board_map, image_url), headers, args.dry_run):
            failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
