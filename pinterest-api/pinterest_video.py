"""Upload a video to Pinterest so a pin can use it (added 22 Oct 2026).

Pinterest takes a video in three steps, and a pin can only be created once
the third says it is ready:

  1. POST /v5/media {"media_type": "video"}  → media_id, upload_url, upload_parameters
  2. POST the file to upload_url as a form, with upload_parameters as fields
  3. GET  /v5/media/<media_id> until status is "succeeded" ("failed" ends it)

The pin then uses media_source {"source_type": "video_id", "media_id": …,
"cover_image_url": …}; the cover is the PNG that pin-studio renders beside
every video.

No token or upload URL is ever printed.
"""

import time

import requests

from pinterest_common import API_BASE

MEDIA_ENDPOINT = f"{API_BASE}/media"
POLL_SECONDS = 10
POLL_LIMIT_SECONDS = 15 * 60


class VideoRefused(Exception):
    """Pinterest would not accept a video upload at all (e.g. the app's access
    level does not include it). The caller may fall back to the cover image."""


class VideoFailed(Exception):
    """The upload started but did not finish; try again next run."""


def upload_video(path, headers, sleep=time.sleep):
    """Upload the MP4 at `path`; return its media_id once Pinterest has processed it."""
    resp = requests.post(MEDIA_ENDPOINT, headers=headers, json={"media_type": "video"}, timeout=60)
    if resp.status_code in (401, 403):
        raise VideoRefused(f"HTTP {resp.status_code} registering the video: {_message(resp)}")
    if resp.status_code not in (200, 201):
        raise VideoFailed(f"HTTP {resp.status_code} registering the video: {_message(resp)}")
    media = resp.json()
    media_id = media["media_id"]

    with open(path, "rb") as fh:
        up = requests.post(media["upload_url"], data=media.get("upload_parameters", {}),
                           files={"file": fh}, timeout=300)
    if up.status_code not in (200, 201, 204):
        raise VideoFailed(f"HTTP {up.status_code} uploading the file")

    waited = 0
    while waited <= POLL_LIMIT_SECONDS:
        check = requests.get(f"{MEDIA_ENDPOINT}/{media_id}", headers=headers, timeout=60)
        status = check.json().get("status") if check.status_code == 200 else None
        if status == "succeeded":
            return media_id
        if status == "failed":
            raise VideoFailed("Pinterest could not process the video")
        sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    raise VideoFailed(f"video still processing after {POLL_LIMIT_SECONDS // 60} minutes")


def _message(resp):
    try:
        return resp.json().get("message", "")[:200]
    except ValueError:
        return resp.text[:200]
