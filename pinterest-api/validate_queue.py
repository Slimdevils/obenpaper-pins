"""Check pins_export.json against Obenpaper's standing Pinterest rules.

Run:  python validate_queue.py

Exit code 1 if any pin breaks a rule. The automatic publisher runs exactly
this check first and publishes nothing while the queue has an error, so a
red check on GitHub means "fix the queue", never "it posted anyway".

Per pin:
  - required fields present; ids unique
  - board category exists (and, when publishing, is mapped to a real board ID)
  - FR pins only on the FR board, and the FR board only takes FR pins
  - destination is https on obenpaper.com or shop.obenpaper.com, no UTM,
    no query string or fragment at all, a confirmed route or a /b/<slug>
  - macro-split is never pinned
  - website boards only take their own routes
  - a store link is in confirmed_links.json (URLs lock on publish, never guessed)
  - guardrail lint passes for the pin's line (+ "general"): an off-limits term
    is an error anywhere; a headline-watch term is an error in the title and a
    warning elsewhere
  - title / description / alt text within Pinterest's limits
  - image is a PNG/JPG (video pins are not supported by this publisher)

Across the whole planned schedule (posted, upcoming and missed alike):
  - never the same product twice in a row
  - never two pins on the same calendar day (Zurich time)
  - a gap over two days is a warning, not an error
"""

import json
import os
import sys
from datetime import datetime
from urllib.parse import urlsplit

from obenpaper_rules import (
    BOARDS,
    IMAGE_EXTENSIONS,
    LIMITS,
    MAX_GAP_DAYS,
    MISSED_AFTER_HOURS,
    NEVER_PIN_SLUGS,
    SHOP_HOST,
    SITE_BOARD_ROUTES,
    SITE_HOST,
    SITE_ROUTES,
    TIMEZONE,
    TOOL_SLUGS,
)
from guardrail_lint import HEADLINE_WATCH, WORDLISTS

HERE = os.path.dirname(os.path.abspath(__file__))
PINS_PATH = os.path.join(HERE, "pins_export.json")
MAP_PATH = os.path.join(HERE, "board_map.json")
POSTED_PATH = os.path.join(HERE, "posted_ids.json")
LINKS_PATH = os.path.join(HERE, "confirmed_links.json")


def confirmed_shop_links():
    with open(LINKS_PATH, "r", encoding="utf-8") as fh:
        return set(json.load(fh)["shop"])

REQUIRED = ["id", "product", "category", "title", "description", "alt_text",
            "link", "scheduled_at", "guardrail"]


def parse_when(value):
    """ISO date-time; a naive value is Zurich local time."""
    when = datetime.fromisoformat(value)
    if when.tzinfo is None:
        when = when.replace(tzinfo=TIMEZONE)
    return when.astimezone(TIMEZONE)


def is_fr(product):
    return product.strip().upper().endswith(" FR")


def check_link(pin, category):
    """Return a list of problems with the destination URL."""
    link = (pin.get("link") or "").strip()
    if not link:
        return [] if category == "scratch" else ["link is empty"]

    problems = []
    if "utm_" in link.lower():
        problems.append("link contains a UTM parameter (organic pins use plain URLs)")
    parts = urlsplit(link)
    if parts.query or parts.fragment or "?" in link or "#" in link:
        problems.append("link has a query string or fragment — plain URL only")
    if parts.scheme != "https":
        problems.append("link must start with https://")

    host = parts.hostname or ""
    path = parts.path.rstrip("/") or "/"

    if host == SHOP_HOST:
        segments = path.strip("/").split("/")
        if len(segments) != 2 or segments[0] != "b" or not segments[1].isalnum():
            problems.append(f"store link must be https://{SHOP_HOST}/b/<slug>, got {path}")
        elif link not in confirmed_shop_links():
            problems.append("store link is not in confirmed_links.json — never guessed")
        if category in SITE_BOARD_ROUTES:
            problems.append("a website board pin must link to obenpaper.com, not straight to the store")
    elif host == SITE_HOST:
        if path.startswith("/tools/"):
            slug = path[len("/tools/"):]
            if slug in NEVER_PIN_SLUGS:
                problems.append(f"/tools/{slug} is a standing exclusion — never pinned")
            elif slug not in TOOL_SLUGS:
                problems.append(f"/tools/{slug} is not a confirmed tool slug")
        elif path not in SITE_ROUTES:
            problems.append(f"{path} is not a confirmed site route")
        rule = SITE_BOARD_ROUTES.get(category)
        if rule and not rule(path):
            problems.append(f"{path} does not belong on the {BOARDS[category]} board")
    else:
        problems.append(f"link host must be {SITE_HOST} or {SHOP_HOST}, got '{host}'")

    raw = pin.get("link") or ""
    if raw != raw.strip() or (parts.path.endswith("/") and parts.path != "/"):
        problems.append("link has a trailing slash or whitespace — use the canonical URL")
    return problems


def check_guardrail(pin):
    """Return (errors, warnings) from the vendored guardrail word lists."""
    line = pin.get("guardrail")
    if line not in WORDLISTS:
        return [f"guardrail '{line}' is not a lint line ({', '.join(WORDLISTS)})"], []
    errors, warnings = [], []
    lines = [line] if line == "general" else [line, "general"]
    for field in ("title", "description", "alt_text"):
        text = " ".join(str(pin.get(field, "")).split()).lower()
        for key in lines:
            for term in WORDLISTS[key]:
                if term.lower() in text:
                    errors.append(f"guardrail ({key}): off-limits term '{term.strip()}' in {field}")
            for term in HEADLINE_WATCH.get(key, []):
                if term.lower() in text:
                    msg = f"guardrail ({key}): '{term}' in {field} — label only, never a selling point"
                    (errors if field == "title" else warnings).append(msg)
    return errors, warnings


def check_pin(pin, board_map, require_boards=True):
    errors = []
    for field in REQUIRED:
        value = pin.get(field)
        if value is None or (isinstance(value, str) and not value.strip() and field != "link"):
            errors.append(f"missing {field}")
    if errors:
        return errors

    category = pin["category"]
    if category not in BOARDS:
        errors.append(f"unknown category '{category}' (boards: {', '.join(BOARDS)})")
    elif require_boards and not board_map.get(category):
        errors.append(f"category '{category}' has no board ID in board_map.json")

    product = pin["product"]
    if category == "cycle_fr" and not is_fr(product):
        errors.append("the FR board only takes FR products (product name must end in ' FR')")
    if is_fr(product) and category != "cycle_fr":
        errors.append("an FR product pins to the FR board only")

    errors.extend(check_link(pin, category))


    for field, limit in LIMITS.items():
        if len(pin[field]) > limit:
            errors.append(f"{field} is {len(pin[field])} chars (limit {limit})")

    image = pin.get("image_file") or pin.get("image_url") or ""
    if not image:
        errors.append("no image_file or image_url")
    elif not image.lower().endswith(IMAGE_EXTENSIONS):
        errors.append("image must be .png or .jpg (video pins are not supported by this publisher)")

    try:
        parse_when(pin["scheduled_at"])
    except (ValueError, TypeError):
        errors.append(f"unparseable scheduled_at '{pin['scheduled_at']}'")
    return errors


def validate(pins, board_map, posted_ids, now=None, require_boards=True):
    """Return (errors, warnings, missed_ids). errors/warnings are strings.

    require_boards=False is for the push check: board IDs are filled in by the
    cloud publisher on its first run, so an unmapped board is only a warning
    until then. The publisher always validates with require_boards=True.
    """
    now = now or datetime.now(TIMEZONE)
    errors, warnings, missed = [], [], set()

    seen = set()
    for pin in pins:
        pid = pin.get("id", "?")
        if pid in seen:
            errors.append(f"{pid}: duplicate id")
        seen.add(pid)
        for problem in check_pin(pin, board_map, require_boards):
            errors.append(f"{pid}: {problem}")
        if pid not in posted_ids and pin.get("guardrail"):
            g_err, g_warn = check_guardrail(pin)
            errors.extend(f"{pid}: {e}" for e in g_err)
            warnings.extend(f"{pid}: {w}" for w in g_warn)
        if not require_boards and pin.get("category") in BOARDS and not board_map.get(pin["category"]):
            warnings.append(f"{pid}: board '{pin['category']}' not mapped yet — filled on the first cloud run")

    dated = []
    for pin in pins:
        try:
            when = parse_when(pin["scheduled_at"])
        except (KeyError, ValueError, TypeError):
            continue
        pid = pin.get("id")
        if pid not in posted_ids and (now - when).total_seconds() > MISSED_AFTER_HOURS * 3600:
            missed.add(pid)
            warnings.append(
                f"{pid}: missed its slot ({when:%a %d %b %H:%M}) — it will NOT be posted late; "
                "give it a new date or remove it"
            )
        # Missed pins stay in the sequence: the PLAN is what gets checked, so
        # an error can only come from an edit, never from time passing.
        dated.append((when, pin))

    dated.sort(key=lambda item: item[0])
    for (prev_when, prev), (when, pin) in zip(dated, dated[1:]):
        if prev.get("product") == pin.get("product"):
            errors.append(
                f"{pin.get('id')}: same product as the pin before it ({prev.get('id')}) — alternate products"
            )
        if prev_when.date() == when.date():
            errors.append(
                f"{pin.get('id')}: same day as {prev.get('id')} ({when:%a %d %b}) — one pin per day"
            )
        elif (when.date() - prev_when.date()).days > MAX_GAP_DAYS:
            warnings.append(
                f"{pin.get('id')}: {(when.date() - prev_when.date()).days}-day gap after {prev.get('id')}"
            )
    return errors, warnings, missed


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_queue():
    pins = load_json(PINS_PATH, [])
    board_map = load_json(MAP_PATH, {})
    posted_ids = {entry["pin"] for entry in load_json(POSTED_PATH, [])}
    return pins, board_map, posted_ids


def main():
    pins, board_map, posted_ids = load_queue()
    if not pins:
        print("pins_export.json is empty or absent — nothing to check.")
        return 0

    errors, warnings, missed = validate(pins, board_map, posted_ids, require_boards=False)
    pending = [p for p in pins if p.get("id") not in posted_ids and p.get("id") not in missed]
    print(f"{len(pins)} pin(s) in the queue: {len(posted_ids & {p.get('id') for p in pins})} posted, "
          f"{len(pending)} upcoming, {len(missed)} missed.")

    for line in warnings:
        print(f"WARNING  {line}")
    for line in errors:
        print(f"ERROR    {line}")

    if errors:
        print(f"\n{len(errors)} error(s). Nothing publishes until the queue is clean.")
        return 1
    print("\nQueue OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
