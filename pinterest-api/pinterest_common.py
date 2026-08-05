"""Shared helpers: config loading, token storage, token refresh, auth headers.

Every other script in this folder imports from here. Nothing in this file
prints a secret value.
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


def mask(value):
    """Return a safe-to-display version of a secret."""
    if not value:
        return "(empty)"
    value = str(value)
    return value[:4] + "..." if len(value) > 4 else "..."


def load_config():
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
    print("config.json parsed OK. Keys present:")
    for key in REQUIRED_KEYS:
        shown = mask(cfg[key]) if key in SECRET_KEYS else cfg[key]
        print(f"  {key}: {shown}")
    return cfg


def save_token(payload):
    payload = dict(payload)
    payload["obtained_at"] = int(time.time())
    with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.chmod(TOKEN_PATH, 0o600)


def load_token():
    if not os.path.exists(TOKEN_PATH):
        sys.exit("token.json not found. Run: python pinterest_auth.py")
    with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def basic_auth_header(cfg):
    raw = f"{cfg['client_id']}:{cfg['client_secret']}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def refresh_token(cfg, token):
    """Exchange the refresh token for a fresh access token."""
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
    # Pinterest does not always return a new refresh token; keep the old one.
    payload.setdefault("refresh_token", token["refresh_token"])
    save_token(payload)
    print("Access token refreshed.")
    return payload


def token_is_stale(token):
    expires_in = token.get("expires_in")
    obtained_at = token.get("obtained_at")
    if not expires_in or not obtained_at:
        return True
    # Refresh a little early rather than mid-run.
    return time.time() > (obtained_at + expires_in - 300)


def get_access_token(cfg=None):
    cfg = cfg or load_config()
    token = load_token()
    if token_is_stale(token):
        token = refresh_token(cfg, token)
    return token["access_token"]


def auth_headers(cfg=None):
    return {
        "Authorization": f"Bearer {get_access_token(cfg)}",
        "Content-Type": "application/json",
    }
