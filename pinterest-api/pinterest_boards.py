"""List the real Pinterest boards on the authorized account and scaffold
board_map.json.

Run:  python pinterest_boards.py

This does NOT guess mappings. It prints every board with its ID and writes
board_map.json with the Obenpaper category keys left as null for you to fill
in deliberately. Per §07a the first board a fresh pin lands on shapes how
Pinterest categorises it, so a wrong mapping is not cosmetic.
"""

import json
import os
import sys

import requests

from obenpaper_rules import BOARDS
from pinterest_common import API_BASE, HERE, auth_headers, load_config

MAP_PATH = os.path.join(HERE, "board_map.json")

# Category keys and board names live in obenpaper_rules.BOARDS (boards.md,
# eight boards as of 18 Aug 2026). Add a key there only when the board
# actually exists on the account.
CATEGORY_KEYS = list(BOARDS)


def fetch_boards(cfg):
    boards = []
    bookmark = None
    while True:
        params = {"page_size": 100}
        if bookmark:
            params["bookmark"] = bookmark
        resp = requests.get(
            f"{API_BASE}/boards",
            headers=auth_headers(cfg),
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            sys.exit(f"Failed to list boards ({resp.status_code}): {resp.text}")
        payload = resp.json()
        boards.extend(payload.get("items", []))
        bookmark = payload.get("bookmark")
        if not bookmark:
            break
    return boards


def main():
    cfg = load_config()
    boards = fetch_boards(cfg)

    if not boards:
        sys.exit("No boards returned. Check the token has boards:read scope.")

    print(f"{len(boards)} board(s) on this account:\n")
    print(f"{'ID':<22} {'PINS':>6}  {'PRIVACY':<8} NAME")
    print("-" * 78)
    for board in sorted(boards, key=lambda b: b.get("name", "")):
        counts = board.get("pin_count")
        if counts is None:
            counts = board.get("board_pins_count", "-")
        print(
            f"{board.get('id', '?'):<22} {str(counts):>6}  "
            f"{board.get('privacy', '-'):<8} {board.get('name', '(unnamed)')}"
        )

    by_name = {b.get("name", "").strip().lower(): b.get("id") for b in boards}
    print("\nExact name matches (confirm each one before copying it into board_map.json):")
    for key, name in BOARDS.items():
        match = by_name.get(name.strip().lower())
        print(f"  {key:<17} {match or '— no board with exactly this name':<36} {name}")

    if os.path.exists(MAP_PATH):
        print(f"\nboard_map.json already exists — leaving it untouched.")
        print("Delete it first if you want a fresh skeleton.")
        return

    skeleton = {key: None for key in CATEGORY_KEYS}
    with open(MAP_PATH, "w", encoding="utf-8") as fh:
        json.dump(skeleton, fh, indent=2)

    print(f"\nWrote board_map.json skeleton with {len(CATEGORY_KEYS)} null keys.")
    print("Fill each one with the board ID from the list above before publishing.")


if __name__ == "__main__":
    main()
