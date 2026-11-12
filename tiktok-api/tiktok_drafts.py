"""Obenpaper TikTok drafts — uploads queued videos to @obenpaper's TikTok INBOX.

Decided 8–12 Nov 2026 (Luc): organic account, sandbox app "Obenpaper test"
(scope video.upload, Direct Post OFF). Every video lands as a DRAFT in the
TikTok app's inbox; Luc adds a trending sound, writes the caption and presses
Publish himself. Nothing is ever posted from here.

Queue:   tiktok/queue.json      (in order)
           video: {"id", "file": "tiktok/videos/x.mp4", "caption", "note"}
           photo: {"id", "type": "photo", "images": ["https://obenpaper.com/tiktok/...jpg", ...],
                   "caption", "note"}  — a carousel. TikTok only PULLS photos from a
                   verified domain (obenpaper.com/ is verified) and refuses PNG.
           Sounds can't be set by API for drafts: put the chosen sound in "note".
Record:  tiktok/uploaded.json   ids already sent to the inbox (never twice)

Token:   TikTok may rotate the refresh token on refresh, so — exactly like the
         Pinterest publisher — the live token is kept encrypted in
         tiktok-api/state/tiktok_token.enc (Fernet, key = PINTEREST_KEY secret)
         and committed back by the workflow. The very first run seeds it from
         the TIKTOK_REFRESH_TOKEN secret. The repo is public: every token is
         masked in the logs before anything else happens.

Secrets: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN (seed),
         PINTEREST_KEY (encryption key, already set for Pinterest).

    python tiktok-api/tiktok_drafts.py            # upload the next queued video
    python tiktok-api/tiktok_drafts.py --dry-run  # say what would be sent
    python tiktok-api/tiktok_drafts.py --id ID    # send that queue entry now
"""

import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
QUEUE_PATH = os.path.join(ROOT, "tiktok", "queue.json")
UPLOADED_PATH = os.path.join(ROOT, "tiktok", "uploaded.json")
TOKEN_ENC_PATH = os.path.join(HERE, "state", "tiktok_token.enc")

API = "https://open.tiktokapis.com/v2"
PHOTO_PREFIX = "https://obenpaper.com/"
MB = 1024 * 1024
# TikTok chunk rules: a file up to 64 MB goes as ONE chunk; above that, chunks
# of 5–64 MB, the last chunk absorbing the remainder (it may reach 128 MB).
SINGLE_CHUNK_MAX = 64 * MB
CHUNK = 10 * MB


# ---------------------------------------------------------------- pure parts

def chunk_plan(size):
    """(chunk_size, total_chunk_count, [(start, end_inclusive), ...])."""
    if size <= 0:
        raise ValueError("empty video")
    if size <= SINGLE_CHUNK_MAX:
        return size, 1, [(0, size - 1)]
    count = size // CHUNK
    ranges = [(i * CHUNK, (i + 1) * CHUNK - 1) for i in range(count - 1)]
    ranges.append(((count - 1) * CHUNK, size - 1))
    return CHUNK, count, ranges


def next_entry(queue, uploaded, wanted_id=None):
    done = set(uploaded)
    for entry in queue:
        if wanted_id and entry["id"] != wanted_id:
            continue
        if entry["id"] in done:
            if wanted_id:
                raise SystemExit(f"{wanted_id} was already sent to the inbox.")
            continue
        return entry
    return None


def validate_queue(queue):
    problems, seen = [], set()
    for i, e in enumerate(queue):
        if not e.get("id"):
            problems.append(f"entry {i}: missing 'id'")
        if e.get("id") in seen:
            problems.append(f"entry {i}: duplicate id {e.get('id')}")
        seen.add(e.get("id"))
        if e.get("type") == "photo":
            imgs = e.get("images") or []
            if not 1 <= len(imgs) <= 35:
                problems.append(f"{e.get('id')}: a carousel needs 1-35 images")
            for u in imgs:
                if not u.startswith(PHOTO_PREFIX):
                    problems.append(f"{e.get('id')}: {u} is not under the verified {PHOTO_PREFIX}")
                if not u.lower().endswith((".jpg", ".jpeg", ".webp")):
                    problems.append(f"{e.get('id')}: {u} must be JPEG or WEBP (TikTok refuses PNG)")
            continue
        if not e.get("file"):
            problems.append(f"entry {i}: missing 'file'")
            continue
        path = os.path.join(ROOT, e["file"])
        if not os.path.isfile(path):
            problems.append(f"{e.get('id')}: file not found: {e['file']}")
        elif not e["file"].lower().endswith(".mp4"):
            problems.append(f"{e.get('id')}: only .mp4 is queued")
    return problems


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- network

def mask(value):
    if value:
        print(f"::add-mask::{value}", flush=True)


def _requests():
    import requests  # imported lazily so the pure parts test without it
    return requests


def refresh(client_key, client_secret, refresh_token):
    r = _requests().post(
        f"{API}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
        data={"client_key": client_key, "client_secret": client_secret,
              "grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=30,
    )
    body = r.json()
    if not body.get("access_token"):
        raise SystemExit(f"TikTok refused the token refresh: {body.get('error')} {body.get('error_description')}")
    mask(body["access_token"])
    mask(body.get("refresh_token"))
    return body


def current_refresh_token(key):
    """Encrypted state wins; the TIKTOK_REFRESH_TOKEN secret only seeds it."""
    if os.path.exists(TOKEN_ENC_PATH):
        from cryptography.fernet import Fernet
        with open(TOKEN_ENC_PATH, "rb") as fh:
            data = json.loads(Fernet(key.strip().encode()).decrypt(fh.read().strip()))
        mask(data["refresh_token"])
        return data["refresh_token"]
    seed = os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip()
    mask(seed)
    if not seed:
        raise SystemExit("No TikTok token yet: set the TIKTOK_REFRESH_TOKEN secret.")
    return seed


def save_refresh_token(key, token_body):
    from cryptography.fernet import Fernet
    os.makedirs(os.path.dirname(TOKEN_ENC_PATH), exist_ok=True)
    payload = {"refresh_token": token_body["refresh_token"],
               "refresh_expires_in": token_body.get("refresh_expires_in"),
               "open_id": token_body.get("open_id"),
               "saved_at": int(time.time())}
    with open(TOKEN_ENC_PATH, "wb") as fh:
        fh.write(Fernet(key.strip().encode()).encrypt(json.dumps(payload).encode()) + b"\n")


def upload_to_inbox(access_token, path):
    rq = _requests()
    size = os.path.getsize(path)
    chunk_size, count, ranges = chunk_plan(size)
    init = rq.post(
        f"{API}/post/publish/inbox/video/init/",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"},
        json={"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                              "chunk_size": chunk_size, "total_chunk_count": count}},
        timeout=30,
    ).json()
    err = init.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise SystemExit(f"TikTok refused the upload: {err.get('code')} {err.get('message')}")
    publish_id, upload_url = init["data"]["publish_id"], init["data"]["upload_url"]

    with open(path, "rb") as fh:
        for start, end in ranges:
            fh.seek(start)
            part = fh.read(end - start + 1)
            res = rq.put(upload_url, data=part, timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            if res.status_code not in (200, 201, 206):
                raise SystemExit(f"Chunk {start}-{end} failed: HTTP {res.status_code}")

    for _ in range(30):
        st = rq.post(f"{API}/post/publish/status/fetch/",
                     headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"},
                     json={"publish_id": publish_id}, timeout=30).json()
        status = st.get("data", {}).get("status")
        if status == "SEND_TO_USER_INBOX" or status == "PUBLISH_COMPLETE":
            return publish_id, status
        if status == "FAILED":
            raise SystemExit(f"TikTok failed the upload: {st.get('data', {}).get('fail_reason')}")
        time.sleep(5)
    return publish_id, status or "UNKNOWN"


def photos_to_inbox(access_token, images, caption=""):
    rq = _requests()
    hdr = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"}
    body = {"media_type": "PHOTO", "post_mode": "MEDIA_UPLOAD",
            "post_info": {"title": "", "description": caption or ""},
            "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": images}}
    init = rq.post(f"{API}/post/publish/content/init/", headers=hdr, json=body, timeout=30).json()
    err = init.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise SystemExit(f"TikTok refused the carousel: {err.get('code')} {err.get('message')}")
    publish_id = init["data"]["publish_id"]
    status = None
    for _ in range(30):
        st = rq.post(f"{API}/post/publish/status/fetch/", headers=hdr, json={"publish_id": publish_id}, timeout=30).json()
        status = st.get("data", {}).get("status")
        if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            return publish_id, status
        if status == "FAILED":
            raise SystemExit(f"TikTok failed the carousel: {st.get('data', {}).get('fail_reason')}")
        time.sleep(5)
    return publish_id, status or "UNKNOWN"


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id")
    args = ap.parse_args()

    queue = load_json(QUEUE_PATH, [])
    uploaded = load_json(UPLOADED_PATH, [])
    problems = validate_queue(queue)
    if problems:
        raise SystemExit("Queue problems:\n  " + "\n  ".join(problems))

    entry = next_entry(queue, [u["id"] for u in uploaded], args.id)
    if not entry:
        print("Nothing queued.")
        return
    is_photo = entry.get("type") == "photo"
    if is_photo:
        print(f"Next: {entry['id']} — carousel of {len(entry['images'])} images")
    else:
        path = os.path.join(ROOT, entry["file"])
        print(f"Next: {entry['id']} — {entry['file']} ({os.path.getsize(path) / MB:.1f} MB)")
    if entry.get("note"):
        print(f"Note: {entry['note']}")
    if args.dry_run:
        print("Dry run: nothing sent.")
        return

    ck, cs, key = (os.environ.get(k, "").strip() for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "PINTEREST_KEY"))
    mask(cs)
    if not (ck and cs and key):
        raise SystemExit("Missing secret: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and PINTEREST_KEY are all needed.")

    token = refresh(ck, cs, current_refresh_token(key))
    # Save the (possibly rotated) refresh token BEFORE uploading, so a failed
    # upload can never strand the only valid token.
    save_refresh_token(key, token)

    if is_photo:
        publish_id, status = photos_to_inbox(token["access_token"], entry["images"], entry.get("caption", ""))
    else:
        publish_id, status = upload_to_inbox(token["access_token"], path)
    uploaded.append({"id": entry["id"], "file": entry.get("file") or "carousel", "publish_id": publish_id,
                     "status": status, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    with open(UPLOADED_PATH, "w", encoding="utf-8") as fh:
        json.dump(uploaded, fh, indent=2)
        fh.write("\n")
    print(f"Sent to the @obenpaper inbox: {entry['id']} ({status}).")
    if entry.get("caption"):
        print(f"Caption to paste:\n{entry['caption']}")


if __name__ == "__main__":
    main()
