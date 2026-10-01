"""Cloud-mode token keeper. Runs at the start of every GitHub Actions run.

Pinterest rotates the refresh token on every refresh: the one sent is spent
and only the new one works (continuous refresh — 30-day access token,
60-day refresh token renewed each time). So this script:

  1. Reads the PINTEREST_TOKEN repository secret (JSON written by
     seed_cloud_token.py or by a previous run of this script).
  2. Masks both tokens in the logs straight away — the repo is public and so
     are its workflow logs.
  3. Refreshes ONLY when needed (access token under 3 days left, or refresh
     token under 14 days left). Most runs refresh nothing.
  4. Before spending the refresh token, checks it can write the secret back;
     after refreshing, writes the new JSON to PINTEREST_TOKEN at once.
  5. Writes the live token to a private temp file for the publish step and
     records non-secret expiry dates in state/token_meta.json.

If PINTEREST_TOKEN is not set yet, it reports "not configured" and the
workflow skips publishing instead of failing every hour.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from pinterest_common import (
    HERE,
    REFRESH_MARGIN_SECONDS,
    load_config,
    request_refresh,
    seconds_left,
    stamp,
)

SECRET_NAME = "PINTEREST_TOKEN"
REFRESH_TOKEN_MARGIN = 14 * 24 * 3600
STATE_DIR = os.path.join(HERE, "state")
META_PATH = os.path.join(STATE_DIR, "token_meta.json")


def gh_output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")


def gh_env(key, value):
    path = os.environ.get("GITHUB_ENV")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")


def add_mask(value):
    if value:
        print(f"::add-mask::{value}", flush=True)


def refresh_expires_at(token):
    if token.get("refresh_token_expires_at"):
        return int(token["refresh_token_expires_at"])
    if token.get("refresh_token_expires_in") and token.get("obtained_at"):
        return int(token["obtained_at"]) + int(token["refresh_token_expires_in"])
    return None


def day(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else "unknown"


def repo():
    return os.environ.get("GITHUB_REPOSITORY", "slimdevils/obenpaper-pins")


def can_write_secret():
    """Pre-flight: the PAT in GH_TOKEN must reach this repo's secrets."""
    if not os.environ.get("GH_TOKEN"):
        return False, "GH_TOKEN is empty — the PINTEREST_SECRETS_PAT secret is not set"
    probe = subprocess.run(
        ["gh", "secret", "list", "--repo", repo()],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        return False, "the PAT cannot read this repo's secrets (needs Secrets: Read and write)"
    return True, ""


def write_secret(token):
    body = json.dumps(token)
    for attempt in range(1, 4):
        result = subprocess.run(
            ["gh", "secret", "set", SECRET_NAME, "--repo", repo()],
            input=body, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return True
        print(f"Saving {SECRET_NAME} failed (attempt {attempt}/3).")
        time.sleep(5)
    return False


def write_meta(token, refreshed):
    os.makedirs(STATE_DIR, exist_ok=True)
    meta = {
        "refreshed_at": day(token.get("obtained_at")) if refreshed else None,
        "access_token_expires": day(token["obtained_at"] + token["expires_in"]),
        "refresh_token_expires": day(refresh_expires_at(token)),
    }
    if not refreshed and os.path.exists(META_PATH):
        with open(META_PATH, "r", encoding="utf-8") as fh:
            meta["refreshed_at"] = json.load(fh).get("refreshed_at")
    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")


def main():
    raw = os.environ.get("PINTEREST_TOKEN", "").strip()
    if not raw:
        print("PINTEREST_TOKEN is not set — the publisher is not configured yet. Skipping.")
        gh_output("configured", "false")
        return 0

    try:
        token = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit("PINTEREST_TOKEN is not valid JSON. Re-seed it with seed_cloud_token.py.")
    add_mask(token.get("access_token"))
    add_mask(token.get("refresh_token"))

    cfg = load_config()
    now = time.time()
    access_left = seconds_left(token)
    refresh_at = refresh_expires_at(token)

    if refresh_at and refresh_at < now:
        sys.exit("The refresh token has expired. Re-authorize locally (pinterest_auth.py) "
                 "and re-seed with seed_cloud_token.py.")

    needs_refresh = (
        access_left is None
        or access_left < REFRESH_MARGIN_SECONDS
        or (refresh_at is not None and refresh_at - now < REFRESH_TOKEN_MARGIN)
    )

    if needs_refresh:
        ok, why = can_write_secret()
        if not ok:
            sys.exit(f"Refresh needed but NOT attempted: {why}. "
                     "Refreshing now would spend the refresh token with nowhere to save "
                     "its replacement.")
        print("Refreshing the Pinterest access token...")
        token = stamp(request_refresh(cfg, token))
        add_mask(token.get("access_token"))
        add_mask(token.get("refresh_token"))
        if not write_secret(token):
            sys.exit("TOKEN ROTATED BUT NOT SAVED. The old refresh token is spent and the new "
                     "one is lost. Re-authorize locally (pinterest_auth.py) and re-seed with "
                     "seed_cloud_token.py before the next run.")
        print(f"Rotated token saved to the {SECRET_NAME} secret.")

    write_meta(token, refreshed=needs_refresh)

    temp_dir = os.environ.get("RUNNER_TEMP") or HERE
    path = os.path.join(temp_dir, "pinterest_token.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(token, fh)
    os.chmod(path, 0o600)
    gh_env("PINTEREST_TOKEN_FILE", path)
    gh_output("configured", "true")

    print(f"Access token valid until {day(token['obtained_at'] + token['expires_in'])}; "
          f"refresh token until {day(refresh_expires_at(token))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
