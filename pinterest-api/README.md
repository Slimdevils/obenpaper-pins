# Obenpaper Pinterest publishing pipeline

Publishes pins to Pinterest via the v5 API instead of the native composer.

- **App:** `Obenpaper_Scheduler`, app ID `1587406`
- **Tier:** TRIAL — pins created via the API are sandboxed (visible only to
  the account owner). Standard access requires a demo video review.
- **Image host:** `slimdevils/obenpaper-pins` — must be **public**.

## Files

| File | Purpose |
|---|---|
| `pinterest_common.py` | Config load, token storage, token refresh, auth headers |
| `pinterest_auth.py` | One-time OAuth flow (localhost:8085 callback) |
| `pinterest_boards.py` | Lists real boards + IDs, scaffolds `board_map.json` |
| `pinterest_upload_images.py` | Uploads PNGs to GitHub, fills `image_url` |
| `pinterest_publish.py` | Publishes due pins via `POST /v5/pins` |
| `make_test_image.py` | Builds the disposable test PNG |

Generated at runtime, never committed: `config.json`, `token.json`,
`pins_export.json`, `board_map.json`, `posted_ids.json`, `images/`.

## First-time setup

1. `python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
2. `pip install -r requirements.txt`
3. `cp config.example.json config.json` and fill in:
   - `client_id` / `client_secret` — Pinterest developer portal
   - `github_token` — fine-grained PAT, **Contents: Read and write**, scoped
     to `slimdevils/obenpaper-pins` only
   - Confirm `github_branch` matches the repo's actual default branch
4. **Add the redirect URI in the Pinterest app settings:**
   `http://localhost:8085/callback` — must match `config.json` exactly or the
   consent step fails.
5. `python pinterest_auth.py` — browser consent, writes `token.json`
6. `python pinterest_boards.py` — prints real boards; fill `board_map.json`
   with the correct IDs by hand. **Do not guess from names.**

## Routine use

1. Export the Scheduler queue as `pins_export.json` (see
   `pins_export.example.json` for the shape). Required per pin: `id`,
   `category`, `image_file`, `title`, `description`, `alt_text`, `link`,
   `scheduled_at`.
2. `python pinterest_upload_images.py` — uploads and verifies public reach
3. `python pinterest_publish.py --dry-run` — inspect payloads
4. `python pinterest_publish.py` — publish

Re-running is safe: `posted_ids.json` prevents double-posting.

## Standing rules enforced here

- **No UTMs.** `pinterest_publish.py` refuses any pin whose `link` contains
  `utm_` (Growth Strategy §3b — plain Payhip URLs only).
- **`max_posts_per_run` = 4.** Pinterest runs spam monitoring on API
  partners. Do not raise this to clear a backlog.
- **Destination URLs lock permanently on publish.** Confirm every URL before
  it ships. Travel Pair pins stay blocked until the Payhip bundle URL exists.

Two rules this pipeline **cannot** enforce, which remain manual judgement:

- **Board-first save.** The API sets `board_id` in the same call that creates
  the pin, which is equivalent — but a wrong `board_map.json` entry
  miscategorises the pin permanently.
- **1–2 day spacing, alternating products.** Enforced by the `scheduled_at`
  dates you set, not by the script.

## Trial vs Standard

On Trial, a create-pin call returns 201 with a real pin ID, but the pin is
not publicly visible. That is expected, not a bug — confirm by loading the
pin URL in a logged-out/incognito window.

For Standard access, submit a demo video via "Mettre à niveau" showing the
full OAuth consent screen and one successful create-pin call. If the app has
already been authorized, revoke it first (Pinterest → Settings → Security →
Apps with access) or the consent screen will be skipped.

## Security

- `config.json` and `token.json` are gitignored and must never be committed.
- `token.json` is written with `0600` permissions.
- No script prints a token, client secret, or PAT.
- The image repo is public by necessity — put **only pin PNGs** in it. No
  PDFs, no product files, no generator scripts.
