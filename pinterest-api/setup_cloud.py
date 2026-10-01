"""ONE-TIME setup of the automatic publisher. The only step Luc runs.

Run from this folder, in your local clone of obenpaper-pins:

    pip install -r requirements.txt
    python setup_cloud.py

It will:
  1. ask for the app's client ID and client secret (Pinterest developer
     portal → Obenpaper_Scheduler) — typed, not shown, never saved in plain text;
  2. open the Pinterest consent screen — click "Give access";
  3. encrypt the credentials and tokens into state/token.enc with a new key;
  4. commit and push state/token.enc;
  5. store the key as the PINTEREST_KEY repository secret — automatically if
     the GitHub CLI (`gh`) is installed and logged in, otherwise it shows the
     key once and the page where to paste it.

After that, nothing else is needed: the hourly workflow keeps the token
alive on its own, and pins are written and queued by Claude.

Run it again only if a workflow run says the token expired or was lost.
"""

import getpass
import json
import os
import shutil
import subprocess
import sys

from pinterest_auth import authorize
from pinterest_common import stamp
from token_store import TOKEN_ENC_PATH, encrypt_bundle, new_key

REPO = "Slimdevils/obenpaper-pins"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
REDIRECT_URI = "http://localhost:8085/callback"


def git(*args):
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


def credentials():
    """Reuse config.json if it exists (from the Trial setup), else ask."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        if cfg.get("client_id") and cfg.get("client_secret") and "PASTE" not in cfg["client_id"]:
            print("Using client ID and secret from config.json.")
            return cfg["client_id"], cfg["client_secret"], cfg.get("redirect_uri") or REDIRECT_URI
    client_id = input("Pinterest app ID (client ID): ").strip()
    client_secret = getpass.getpass("Pinterest app secret (hidden as you type): ").strip()
    if not client_id or not client_secret:
        sys.exit("Both values are needed.")
    return client_id, client_secret, REDIRECT_URI


def main():
    print("Updating the local clone...")
    git("pull", "--rebase", "origin", "main")

    client_id, client_secret, redirect_uri = credentials()
    cfg = {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}

    print("\nOpening Pinterest — click 'Give access' in the browser.")
    payload = authorize(cfg)
    if not payload.get("refresh_token"):
        sys.exit("Pinterest returned no refresh token — nothing was saved.")

    key = new_key()
    bundle = stamp({**payload, "client_id": client_id, "client_secret": client_secret})
    encrypt_bundle(bundle, key)
    print("Token encrypted into state/token.enc.")

    git("add", os.path.relpath(TOKEN_ENC_PATH, REPO_ROOT))
    git("commit", "-m", "Set up the Pinterest publisher token [skip ci]")
    git("push", "origin", "HEAD:main")
    print("Pushed.")

    if shutil.which("gh"):
        result = subprocess.run(["gh", "secret", "set", "PINTEREST_KEY", "--repo", REPO],
                                input=key, capture_output=True, text=True)
        if result.returncode == 0:
            print("\nPINTEREST_KEY secret set via gh. Setup complete — nothing else to do.")
            return
        print(f"\ngh could not set the secret ({result.stderr.strip()}). Do it by hand:")

    print("\nLast step — store the key as a repository secret:")
    print(f"  1. Open https://github.com/{REPO}/settings/secrets/actions/new")
    print("  2. Name:   PINTEREST_KEY")
    print(f"  3. Secret: {key}")
    print("\nThis key is shown once and saved nowhere else. Setup is complete once it is pasted.")


if __name__ == "__main__":
    main()
