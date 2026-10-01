"""Encrypted token store for the cloud publisher.

The Pinterest credentials (client id + secret) and tokens live in
state/token.enc, encrypted with Fernet (AES + HMAC). The only key is the
PINTEREST_KEY repository secret. The repo is public, so the ciphertext is
public too — that is what Fernet is for: without the key it is useless.

Why a file in the repo and not a GitHub secret: Pinterest rotates the refresh
token on every refresh (the old one is spent at once), so the new one must be
saved by the workflow itself. A workflow can commit a file with its built-in
token, but it cannot write a secret without an extra personal access token —
which would be one more thing for Luc to create and renew.
"""

import json
import os

from cryptography.fernet import Fernet, InvalidToken

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "state")
TOKEN_ENC_PATH = os.path.join(STATE_DIR, "token.enc")

BUNDLE_KEYS = ("client_id", "client_secret", "access_token", "refresh_token",
               "expires_in", "obtained_at")


def new_key():
    return Fernet.generate_key().decode("ascii")


def encrypt_bundle(bundle, key, path=TOKEN_ENC_PATH):
    missing = [k for k in BUNDLE_KEYS if not bundle.get(k)]
    if missing:
        raise ValueError("token bundle is missing: " + ", ".join(missing))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = Fernet(key.encode("ascii")).encrypt(json.dumps(bundle).encode("utf-8"))
    with open(path, "wb") as fh:
        fh.write(data + b"\n")


def decrypt_bundle(key, path=TOKEN_ENC_PATH):
    with open(path, "rb") as fh:
        data = fh.read().strip()
    try:
        return json.loads(Fernet(key.strip().encode("ascii")).decrypt(data))
    except (InvalidToken, ValueError) as exc:
        raise SystemExit(
            "state/token.enc cannot be decrypted with PINTEREST_KEY — the key does not "
            "match. Run setup_cloud.py again."
        ) from exc
