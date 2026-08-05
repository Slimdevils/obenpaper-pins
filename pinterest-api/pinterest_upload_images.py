"""Push local pin PNGs to the public GitHub repo and fill image_url in
pins_export.json.

Run:  python pinterest_upload_images.py

Pinterest's create-pin endpoint fetches the image anonymously from a public
URL, so the host repo must be PUBLIC. Each pin in pins_export.json needs an
"image_file" naming a PNG inside images_dir; this script uploads it and
writes back the raw.githubusercontent.com URL as "image_url".

Verify with:  python pinterest_upload_images.py --verify
"""

import argparse
import base64
import json
import os
import sys

import requests

from pinterest_common import HERE, load_config

PINS_PATH = os.path.join(HERE, "pins_export.json")
GITHUB_API = "https://api.github.com"


def github_headers(cfg):
    return {
        "Authorization": f"Bearer {cfg['github_token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def raw_url(cfg, filename):
    path = cfg["github_path"].strip("/")
    prefix = f"{path}/" if path else ""
    return (
        f"https://raw.githubusercontent.com/{cfg['github_owner']}/"
        f"{cfg['github_repo']}/{cfg['github_branch']}/{prefix}{filename}"
    )


def load_pins():
    if not os.path.exists(PINS_PATH):
        sys.exit(
            "pins_export.json not found. Export it from the Studio's "
            "Scheduler tab into this folder."
        )
    with open(PINS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_pins(pins):
    with open(PINS_PATH, "w", encoding="utf-8") as fh:
        json.dump(pins, fh, indent=2, ensure_ascii=False)


def existing_sha(cfg, remote_path):
    """Return the blob SHA if the file already exists, else None."""
    resp = requests.get(
        f"{GITHUB_API}/repos/{cfg['github_owner']}/{cfg['github_repo']}/contents/{remote_path}",
        headers=github_headers(cfg),
        params={"ref": cfg["github_branch"]},
        timeout=30,
    )
    if resp.status_code == 200:
        return resp.json().get("sha")
    if resp.status_code == 404:
        return None
    sys.exit(f"GitHub lookup failed ({resp.status_code}): {resp.text}")


def upload(cfg, local_path, filename):
    path = cfg["github_path"].strip("/")
    remote_path = f"{path}/{filename}" if path else filename

    with open(local_path, "rb") as fh:
        content = base64.b64encode(fh.read()).decode("ascii")

    body = {
        "message": f"Add pin image {filename}",
        "content": content,
        "branch": cfg["github_branch"],
    }
    sha = existing_sha(cfg, remote_path)
    if sha:
        body["sha"] = sha
        body["message"] = f"Update pin image {filename}"

    resp = requests.put(
        f"{GITHUB_API}/repos/{cfg['github_owner']}/{cfg['github_repo']}/contents/{remote_path}",
        headers=github_headers(cfg),
        json=body,
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        sys.exit(f"Upload of {filename} failed ({resp.status_code}): {resp.text}")
    return raw_url(cfg, filename)


def verify(url):
    """Anonymous fetch — exactly what Pinterest's servers will do."""
    resp = requests.get(url, timeout=30)
    ctype = resp.headers.get("Content-Type", "")
    ok = resp.status_code == 200 and ctype.startswith("image/")
    print(f"  {resp.status_code}  {ctype:<24} {url}")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only re-check existing image_urls, upload nothing.",
    )
    args = parser.parse_args()

    cfg = load_config()
    pins = load_pins()

    if args.verify:
        print("Anonymous fetch check (no auth header, as Pinterest would):")
        failures = [p for p in pins if p.get("image_url") and not verify(p["image_url"])]
        if failures:
            sys.exit(
                f"\n{len(failures)} image URL(s) not publicly fetchable. "
                "Is the repo public?"
            )
        print("\nAll image URLs are publicly fetchable.")
        return

    changed = 0
    for pin in pins:
        if pin.get("image_url"):
            continue
        filename = pin.get("image_file")
        if not filename:
            print(f"  SKIP {pin.get('id', '?')} — no image_file field")
            continue
        local_path = os.path.join(cfg["images_dir"], filename)
        if not os.path.exists(local_path):
            print(f"  SKIP {pin.get('id', '?')} — not found: {local_path}")
            continue

        url = upload(cfg, local_path, filename)
        pin["image_url"] = url
        changed += 1
        print(f"  UPLOADED {filename}")

    if changed:
        save_pins(pins)
        print(f"\n{changed} image(s) uploaded, pins_export.json updated.")
    else:
        print("\nNothing to upload.")

    print("\nVerifying public reachability...")
    failures = [p for p in pins if p.get("image_url") and not verify(p["image_url"])]
    if failures:
        sys.exit(f"\n{len(failures)} image URL(s) not publicly fetchable.")


if __name__ == "__main__":
    main()
