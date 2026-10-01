"""Hand the locally-authorized token to the cloud publisher, once.

Run (after pinterest_auth.py):  python seed_cloud_token.py

Writes token.json into the PINTEREST_TOKEN secret of slimdevils/obenpaper-pins,
then DELETES the local token.json. Both copies must never be live at once:
Pinterest spends the refresh token on every refresh, so whichever side
refreshed second would find its token dead.

Uses the GitHub CLI (`gh`) if it is installed and logged in. Otherwise it
tells you where to paste the value by hand and waits for you to confirm.
"""

import json
import os
import shutil
import subprocess
import sys

from pinterest_common import TOKEN_PATH, load_config, load_token, refresh_token, token_is_stale

REPO = "slimdevils/obenpaper-pins"
SECRET_NAME = "PINTEREST_TOKEN"


def main():
    cfg = load_config()
    token = load_token()
    if token_is_stale(token, margin=3 * 24 * 3600):
        token = refresh_token(cfg, token)
    if not token.get("refresh_token"):
        sys.exit("token.json has no refresh token — run pinterest_auth.py again.")

    body = json.dumps(token)

    if shutil.which("gh"):
        result = subprocess.run(
            ["gh", "secret", "set", SECRET_NAME, "--repo", REPO],
            input=body, capture_output=True, text=True,
        )
        if result.returncode != 0:
            sys.exit(f"gh could not set the secret: {result.stderr.strip()}\n"
                     "token.json was left in place.")
        print(f"{SECRET_NAME} secret set on {REPO} via gh.")
    else:
        print("GitHub CLI not found. Set the secret by hand:")
        print(f"  1. Open https://github.com/{REPO}/settings/secrets/actions")
        print(f"  2. New repository secret, name: {SECRET_NAME}")
        print(f"  3. Value: the full contents of {TOKEN_PATH}")
        answer = input("\nType SAVED once the secret is stored (anything else aborts): ")
        if answer.strip().upper() != "SAVED":
            sys.exit("Aborted. token.json was left in place.")

    os.remove(TOKEN_PATH)
    print("Local token.json deleted — the cloud publisher now owns the token.")
    print("Do not publish locally from here on (--dry-run still works without a token).")


if __name__ == "__main__":
    main()
