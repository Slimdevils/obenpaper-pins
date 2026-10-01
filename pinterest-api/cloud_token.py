"""Cloud-mode token keeper. Runs at the start of every GitHub Actions run.

Pinterest rotates the refresh token on every refresh: the one sent is spent
and only the new one works (30-day access token, 60-day refresh token renewed
each time). So this script:

  1. Decrypts state/token.enc with the PINTEREST_KEY secret.
  2. Masks the tokens and client secret in the logs straight away — the repo
     is public and so are its workflow logs.
  3. Refreshes ONLY when needed (access token under 3 days left, or refresh
     token under 14 days left). Most runs refresh nothing.
  4. Before spending the refresh token, checks it can push to the repo;
     after refreshing, re-encrypts, commits and pushes state/token.enc at once,
     before anything else happens.
  5. Writes the live bundle to a private temp file for the later steps.

If PINTEREST_KEY or state/token.enc is missing, it reports "not configured"
and the workflow skips publishing instead of failing every hour.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from pinterest_common import REFRESH_MARGIN_SECONDS, request_refresh, seconds_left, stamp
from token_store import STATE_DIR, TOKEN_ENC_PATH, decrypt_bundle, encrypt_bundle

REFRESH_TOKEN_MARGIN = 14 * 24 * 3600
META_PATH = os.path.join(STATE_DIR, "token_meta.json")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=check)


def can_push():
    result = git("push", "--dry-run", "origin", "HEAD:main", check=False)
    return result.returncode == 0


def push_state(message):
    """Commit and push state/ now. Returns True once it is on origin/main."""
    git("config", "user.name", "obenpaper-publisher")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "pinterest-api/state")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return True
    git("commit", "-m", message)
    for _ in range(4):
        if git("pull", "--rebase", "origin", "main", check=False).returncode == 0 and \
                git("push", "origin", "HEAD:main", check=False).returncode == 0:
            return True
        time.sleep(8)
    return False


def write_meta(token, refreshed):
    os.makedirs(STATE_DIR, exist_ok=True)
    previous = {}
    if os.path.exists(META_PATH):
        with open(META_PATH, "r", encoding="utf-8") as fh:
            previous = json.load(fh)
    meta = {
        "refreshed_at": day(token["obtained_at"]) if refreshed else previous.get("refreshed_at"),
        "access_token_expires": day(token["obtained_at"] + token["expires_in"]),
        "refresh_token_expires": day(refresh_expires_at(token)),
    }
    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")


def main():
    key = os.environ.get("PINTEREST_KEY", "").strip()
    if not key or not os.path.exists(TOKEN_ENC_PATH):
        print("Publisher not configured yet (PINTEREST_KEY or state/token.enc missing). "
              "Run setup_cloud.py once. Skipping.")
        gh_output("configured", "false")
        return 0
    add_mask(key)

    bundle = decrypt_bundle(key)
    for field in ("access_token", "refresh_token", "client_secret"):
        add_mask(bundle.get(field))

    now = time.time()
    access_left = seconds_left(bundle)
    refresh_at = refresh_expires_at(bundle)
    if refresh_at and refresh_at < now:
        sys.exit("The Pinterest refresh token has expired. Run setup_cloud.py again.")

    needs_refresh = (
        access_left is None
        or access_left < REFRESH_MARGIN_SECONDS
        or (refresh_at is not None and refresh_at - now < REFRESH_TOKEN_MARGIN)
    )

    if needs_refresh:
        if not can_push():
            sys.exit("Refresh needed but NOT attempted: this run cannot push to the repo, so the "
                     "rotated token would have nowhere to go.")
        print("Refreshing the Pinterest access token...")
        payload = request_refresh(bundle, bundle)
        add_mask(payload.get("access_token"))
        add_mask(payload.get("refresh_token"))
        bundle = stamp({**bundle, **payload})
        encrypt_bundle(bundle, key)
        write_meta(bundle, refreshed=True)
        if not push_state("Rotate Pinterest token [skip ci]"):
            sys.exit("TOKEN ROTATED BUT NOT PUSHED. The old refresh token is spent; the new one "
                     "is only on this runner. Run setup_cloud.py again.")
        print("Rotated token encrypted and pushed (state/token.enc).")
    elif not os.path.exists(META_PATH):
        write_meta(bundle, refreshed=False)

    temp_dir = os.environ.get("RUNNER_TEMP") or STATE_DIR
    path = os.path.join(temp_dir, "pinterest_token.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh)
    os.chmod(path, 0o600)
    gh_env("PINTEREST_TOKEN_FILE", path)
    gh_output("configured", "true")

    print(f"Access token valid until {day(bundle['obtained_at'] + bundle['expires_in'])}; "
          f"refresh token until {day(refresh_expires_at(bundle))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
