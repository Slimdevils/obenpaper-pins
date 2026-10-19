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
    """Run git; return True on success. Never stops the setup: a failed push
    must not lose the key (that is what happened on 19 Oct 2026)."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}   # never stop to ask for a GitHub login
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, env=env)
    return result.returncode == 0


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
    print("Mise à jour du dossier...")
    if not git("pull", "--rebase", "origin", "main"):
        print("  (mise à jour impossible — on continue quand même)")

    client_id, client_secret, redirect_uri = credentials()
    cfg = {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}

    print("\nPinterest va s'ouvrir dans le navigateur — clique sur « Give access ».")
    payload = authorize(cfg)
    if not payload.get("refresh_token"):
        sys.exit("Pinterest n'a pas renvoyé de refresh token — rien n'a été enregistré.")

    key = new_key()
    bundle = stamp({**payload, "client_id": client_id, "client_secret": client_secret})
    encrypt_bundle(bundle, key)
    print("Token chiffré dans pinterest-api/state/token.enc.")

    rel = os.path.relpath(TOKEN_ENC_PATH, REPO_ROOT)
    git("add", rel)
    git("commit", "-m", "Set up the Pinterest publisher token [skip ci]")
    if git("push", "origin", "HEAD:main"):
        print("Fichier envoyé sur GitHub.")
    else:
        print("Envoi sur GitHub impossible depuis ce Mac — pas grave : dis à Claude "
              "« c'est fait », il enverra le fichier lui-même.")

    if shutil.which("gh"):
        result = subprocess.run(["gh", "secret", "set", "PINTEREST_KEY", "--repo", REPO],
                                input=key, capture_output=True, text=True)
        if result.returncode == 0:
            print("\nClé PINTEREST_KEY enregistrée sur GitHub. Terminé.")
            return

    print("\n" + "=" * 64)
    print("DERNIÈRE ÉTAPE — enregistrer la clé sur GitHub :")
    print(f"  1. Ouvre https://github.com/{REPO}/settings/secrets/actions/new")
    print("  2. Name :   PINTEREST_KEY")
    print(f"  3. Secret : {key}")
    print("  4. Clique « Add secret ».")
    print("=" * 64)
    print("Cette clé n'est affichée qu'une fois et n'est enregistrée nulle part ailleurs.")


if __name__ == "__main__":
    main()
