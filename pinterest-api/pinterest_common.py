"""Shared helpers: config loading, token storage, token refresh, auth headers.

Two modes:
  - LOCAL (default): config.json + token.json in this folder, as before.
  - CLOUD (OBENPAPER_CLOUD=1, set by the GitHub Actions workflow): the
    credentials and the access token come from the file that cloud_token.py
    decrypts from state/token.enc. In cloud mode this module never refreshes the token
    itself — cloud_token.py owns rotation, because Pinterest spends the old
    refresh token on every refresh and the new one must be saved at once.

Nothing in this file prints a secret value.
"""

import base64
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
TOKEN_PATH = os.path.join(HERE, "token.json")

API_BASE = "https://api.pinterest.com/v5"
TOKEN_URL = f"{API_BASE}/oauth/token"

CLOUD = os.environ.get("OBENPAPER_CLOUD") == "1"

REQUIRED_KEYS = [
    "client_id",
    "client_secret",
    "redirect_uri",
    "github_token",
    "github_owner",
    "github_repo",
    "github_branch",
    "github_path",
    "images_dir",
    "max_posts_per_run",
]

SECRET_KEYS = {"client_secret", "github_token"}

# Refresh this long before the access token runs out (it lasts 30 days).
REFRESH_MARGIN_SECONDS = 3 * 24 * 3600


def mask(value):
    """Return a safe-to-display version of a secret."""
    if not value:
        return "(empty)"
    value = str(value)
    return value[:4] + "..." if len(value) > 4 else "..."


def _cloud_config():
    """Cloud mode: credentials come from the decrypted bundle that
    cloud_token.py wrote to PINTEREST_TOKEN_FILE (never from the repo)."""
    owner, _, repo = os.environ.get("GITHUB_REPOSITORY", "Slimdevils/obenpaper-pins").partition("/")
    bundle = {}
    path = os.environ.get("PINTEREST_TOKEN_FILE")
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            bundle = json.load(fh)
    cfg = {
        "client_id": bundle.get("client_id", ""),
        "client_secret": bundle.get("client_secret", ""),
        "github_owner": owner,
        "github_repo": repo,
        "github_branch": os.environ.get("GITHUB_REF_NAME", "main"),
        "github_path": "pins",
        "images_dir": os.path.join(os.path.dirname(HERE), "pins"),
        "max_posts_per_run": int(os.environ.get("MAX_POSTS_PER_RUN", "1")),
    }
    if not cfg["client_id"] or not cfg["client_secret"]:
        sys.exit("Cloud mode has no credentials — cloud_token.py must run first.")
    return cfg


def load_config():
    if CLOUD:
        return _cloud_config()
    if not os.path.exists(CONFIG_PATH):
        sys.exit(
            "config.json not found. Copy config.example.json to config.json "
            "and fill it in."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        try:
            cfg = json.load(fh)
        except json.JSONDecodeError as exc:
            sys.exit(f"config.json is not valid JSON: {exc}")

    missing = [k for k in REQUIRED_KEYS if not cfg.get(k) and cfg.get(k) != 0]
    if missing:
        sys.exit("config.json is missing or has empty values for: " + ", ".join(missing))
    return cfg


def check_config():
    """Verify config without exposing secrets. Used by the setup step."""
    cfg = load_config()
    print("config parsed OK. Keys present:")
    for key in sorted(cfg):
        shown = mask(cfg[key]) if key in SECRET_KEYS else cfg[key]
        print(f"  {key}: {shown}")
    return cfg


def stamp(payload):
    payload = dict(payload)
    payload["obtained_at"] = int(time.time())
    return payload


def save_token(payload, path=TOKEN_PATH):
    payload = stamp(payload)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.chmod(path, 0o600)
    return payload


def load_token():
    path = os.environ.get("PINTEREST_TOKEN_FILE") if CLOUD else TOKEN_PATH
    if not path or not os.path.exists(path):
        if CLOUD:
            sys.exit("No token file — cloud_token.py must run before this step.")
        sys.exit("token.json not found. Run: python pinterest_auth.py")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def basic_auth_header(cfg):
    raw = f"{cfg['client_id']}:{cfg['client_secret']}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def request_refresh(cfg, token):
    """Exchange the refresh token for new tokens. Returns the raw payload.

    Pinterest rotates the refresh token: the one sent here is spent, and the
    payload carries its replacement. The caller MUST persist the payload.
    """
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": basic_auth_header(cfg),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        },
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"Token refresh failed ({resp.status_code}): {resp.text}")
    payload = resp.json()
    # Older apps may not get a new refresh token back; keep the old one then.
    payload.setdefault("refresh_token", token["refresh_token"])
    return payload


def refresh_token(cfg, token):
    """LOCAL mode: refresh and write token.json straight away."""
    payload = save_token(request_refresh(cfg, token))
    print("Access token refreshed.")
    return payload


def seconds_left(token):
    expires_in = token.get("expires_in")
    obtained_at = token.get("obtained_at")
    if not expires_in or not obtained_at:
        return None
    return obtained_at + expires_in - time.time()


def token_is_stale(token, margin=300):
    left = seconds_left(token)
    return left is None or left < margin


def get_access_token(cfg=None):
    cfg = cfg or load_config()
    token = load_token()
    if CLOUD:
        if token_is_stale(token):
            sys.exit("Cloud token is stale — cloud_token.py should have refreshed it.")
        return token["access_token"]
    if token_is_stale(token):
        token = refresh_token(cfg, token)
    return token["access_token"]


def auth_headers(cfg=None):
    return {
        "Authorization": f"Bearer {get_access_token(cfg)}",
        "Content-Type": "application/json",
    }
