"""Publish due pins to Pinterest via POST /v5/pins.

Run:  python pinterest_publish.py --dry-run     (shows payloads, sends nothing)
      python pinterest_publish.py               (publishes)
      python pinterest_publish.py --pin SP-1    (single pin, ignores schedule)

Safe to re-run: posted pin IDs are recorded in posted_ids.json and skipped.

Output is deliberately verbose — the full endpoint, request body, status code
and response body are printed, because this is the shot the Pinterest
Standard-access demo video needs. No token or secret is ever printed.

Standing rules (Project Context v32 §07a / Growth Strategy §3b):
  - destination URLs are plain Payhip URLs, NO UTM parameters
  - destination URLs lock permanently on publish
  - pacing stays near the manual cadence; max_posts_per_run defaults to 4
"""

import argparse
import json
import os
import sys
from datetime import datetime

import requests

from pinterest_common import API_BASE, HERE, auth_headers, load_config

PINS_PATH = os.path.join(HERE, "pins_export.json")
MAP_PATH = os.path.join(HERE, "board_map.json")
POSTED_PATH = os.path.join(HERE, "posted_ids.json")

PINS_ENDPOINT = f"{API_BASE}/pins"


def load_json(path, what):
    if not os.path.exists(path):
        sys.exit(f"{what} not found at {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_posted():
    if not os.path.exists(POSTED_PATH):
        return []
    with open(POSTED_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def record_posted(entry):
    posted = load_posted()
    posted.append(entry)
    with open(POSTED_PATH, "w", encoding="utf-8") as fh:
        json.dump(posted, fh, indent=2, ensure_ascii=False)


def is_due(pin, now):
    when = pin.get("scheduled_at")
    if not when:
        return False
    try:
        return datetime.fromisoformat(when) <= now
    except ValueError:
        print(f"  WARNING {pin.get('id')} — unparseable scheduled_at: {when}")
        return False


def build_payload(pin, board_map):
    category = pin.get("category")
    board_id = board_map.get(category)
    if not board_id:
        return None, f"no board ID mapped for category '{category}'"

    link = (pin.get("link") or "").strip()
    if "utm_" in link:
        return None, "link contains UTM parameters (organic pins must use plain URLs)"

    if not pin.get("image_url"):
        return None, "image_url is empty — run pinterest_upload_images.py first"

    payload = {
        "board_id": board_id,
        "title": pin.get("title", "")[:100],
        "description": pin.get("description", "")[:500],
        "alt_text": pin.get("alt_text", "")[:500],
        "media_source": {
            "source_type": "image_url",
            "url": pin["image_url"],
        },
    }
    if link:
        payload["link"] = link
    return payload, None


def publish(pin, payload, headers, dry_run):
    print(f"\n--- {pin.get('id', '?')} · {pin.get('product', '')} ---")
    print(f"POST {PINS_ENDPOINT}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if dry_run:
        print("DRY RUN — not sent.")
        return True

    resp = requests.post(PINS_ENDPOINT, headers=headers, json=payload, timeout=60)
    print(f"HTTP {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(resp.text)

    if resp.status_code not in (200, 201):
        print(f"FAILED — {pin.get('id')} not recorded as posted.")
        return False

    pin_id = resp.json().get("id")
    record_posted(
        {
            "pin": pin.get("id"),
            "pinterest_pin_id": pin_id,
            "posted_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    print(f"OK — Pinterest pin ID {pin_id} recorded in posted_ids.json")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show payloads, send nothing.")
    parser.add_argument("--pin", help="Publish one pin by its id, ignoring the schedule.")
    args = parser.parse_args()

    cfg = load_config()
    pins = load_json(PINS_PATH, "pins_export.json")
    board_map = load_json(MAP_PATH, "board_map.json")

    unmapped = [k for k, v in board_map.items() if not v]
    if unmapped:
        print(f"NOTE: unmapped board categories (pins using them will be skipped): {', '.join(unmapped)}")

    posted_ids = {entry["pin"] for entry in load_posted()}
    now = datetime.now()

    if args.pin:
        queue = [p for p in pins if p.get("id") == args.pin]
        if not queue:
            sys.exit(f"No pin with id '{args.pin}' in pins_export.json")
    else:
        queue = [p for p in pins if p.get("id") not in posted_ids and is_due(p, now)]

    cap = int(cfg.get("max_posts_per_run", 4))
    if len(queue) > cap:
        print(f"{len(queue)} pins due; capping this run at max_posts_per_run={cap}.")
        queue = queue[:cap]

    if not queue:
        print("Nothing due. Exiting.")
        return

    headers = None if args.dry_run else auth_headers(cfg)

    sent = 0
    for pin in queue:
        payload, problem = build_payload(pin, board_map)
        if problem:
            print(f"\nSKIP {pin.get('id', '?')} — {problem}")
            continue
        if publish(pin, payload, headers, args.dry_run):
            sent += 1

    verb = "would be sent" if args.dry_run else "published"
    print(f"\n{sent} pin(s) {verb}.")


if __name__ == "__main__":
    main()
