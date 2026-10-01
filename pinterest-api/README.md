# Obenpaper Pinterest publisher

Publishes Obenpaper's pins through the Pinterest v5 API, **automatically,
from GitHub Actions** — every hour it checks the queue and posts what is due.
Organic only, written by hand, posted on schedule by our own code.

- **App:** `Obenpaper_Scheduler`, app ID `1587406`
- **Tier:** **STANDARD** (since 1 Oct 2026) — API pins are public.
- **Repo:** `slimdevils/obenpaper-pins` — **public**, because Pinterest fetches
  pin images anonymously. Its Actions logs are public too: no script ever
  prints a token, and the token keeper masks both tokens before anything else.

## How it works

```
pins_export.json  ──►  every hour (:17)  ──►  validate_queue  ──►  cloud_token  ──►  publish ≤1 pin  ──►  posted_ids.json
 (you write it)        GitHub Actions          rules check         keep token          POST /v5/pins       (committed back)
```

1. **You** write pins into `pinterest-api/pins_export.json` (format below),
   commit the images into `pins/`, and push.
2. On the push, GitHub runs the tests and checks the queue. A red ✗ on the
   commit means a pin breaks a rule — the log says which and why.
3. Every hour the publisher posts **at most one** pin whose `scheduled_at`
   (Zurich time) has passed, then records it in `posted_ids.json`.
4. A pin more than **24 h late** (GitHub outage, queue broken) is **never
   posted late** — it is reported as missed. Give it a new date.

## Pin format

```json
{
  "id": "SP-1",
  "product": "Student Planner",
  "category": "student_planner",
  "image_file": "sp-1.png",
  "image_url": "",
  "title": "…",
  "description": "…",
  "alt_text": "…",
  "link": "https://shop.obenpaper.com/b/YpUmC",
  "link_confirmed": true,
  "scheduled_at": "2026-10-06T19:00:00"
}
```

- `category` — one of the board keys in `obenpaper_rules.py` (`BOARDS`).
- `image_file` — a PNG/JPG committed in `pins/`. `image_url` fills itself.
- `link_confirmed` — set to `true` only once Luc has confirmed the URL.
  **Destination URLs lock permanently on publish.**
- `scheduled_at` — Zurich local time unless an offset is given.
- `product` — used for alternation. FR products end in ` FR`.

See `pins_export.example.json`. Pin **copy** follows the
`obenpaper-pinterest-pins` skill and must pass `obenpaper-guardrail-lint`
before it goes in the file — this repo checks the rules, not the wording.

## Rules the publisher enforces (refuses the whole queue on any error)

| Rule | Check |
|---|---|
| Organic, plain URLs | no `utm_`, no query string or fragment, https only |
| Owned destinations only | `obenpaper.com` confirmed routes, or `shop.obenpaper.com/b/<slug>` |
| `macro-split` never pinned | standing exclusion |
| Website boards link to the site | *Free Planner Tools & Quizzes* → `/quiz`, `/tools…`, `/focus`; *Custom & Personalised Planners* → `/made-to-order` |
| FR stays on the FR board | both directions |
| URL confirmed before publish | `link_confirmed: true` |
| Board exists | category mapped to a real ID in `board_map.json` |
| Alternate products | never the same product twice in a row |
| 1–2 day spacing | never two pins on one day (Zurich); over 2 days = warning |
| Pinterest limits | title 100, description/alt 500 — refused, never truncated |
| No burst | max 1 pin per run; missed pins never posted late |
| Board-first save | the API sets `board_id` in the create call itself |

Video pins are not supported by this publisher (refused by the check).

## One-time setup

### 1. Repository secrets

`https://github.com/slimdevils/obenpaper-pins/settings/secrets/actions` →
*New repository secret*:

| Secret | Value |
|---|---|
| `PINTEREST_CLIENT_ID` | from the Pinterest developer portal |
| `PINTEREST_CLIENT_SECRET` | from the Pinterest developer portal |
| `PINTEREST_SECRETS_PAT` | fine-grained PAT, repo `slimdevils/obenpaper-pins` only, permission **Secrets: Read and write** |
| `PINTEREST_TOKEN` | set by `seed_cloud_token.py` (step 2) |

**Why the PAT:** Pinterest rotates the refresh token on every refresh — the
old one is spent and only the new one works (30-day access token, 60-day
refresh token renewed each time). The workflow must write the new one back
into `PINTEREST_TOKEN`, and GitHub's built-in token cannot write secrets.
The PAT's own expiry date is the one date to watch: when it lapses, the next
refresh is refused (safely — the token is never spent without being saved).

### 2. Authorize once, hand the token to the cloud

```
python pinterest_auth.py        # browser consent, writes token.json
python seed_cloud_token.py      # copies it into PINTEREST_TOKEN, deletes token.json
```

From here on the **cloud owns the token**. Do not publish locally: a local
refresh would spend the refresh token the cloud depends on. `--dry-run`
works locally without a token.

### 3. Map the boards

Actions → *Publish pins* → *Run workflow* → mode **list-boards**. The log
lists every board with its ID and the exact-name matches. Confirm each one,
put the IDs into `pinterest-api/board_map.json`, commit, push.

### 4. Check it

Actions → *Run workflow* → mode **dry-run**: shows the payloads it would send.

## Day-to-day

- Add pins + images, push, wait for the green ✓.
- `posted_ids.json` is the record of what went out (pin id → Pinterest pin
  id, link, time). Pull before editing the queue — the workflow commits to it.
- `state/token_meta.json` shows when the token was last rotated and when it
  expires. The rotation commit (every ~27 days) also keeps GitHub from
  pausing the hourly schedule, which it does after 60 days without commits.
- Re-authorize (step 2) only if a run says the refresh token expired or was
  lost.

## Files

| File | Purpose |
|---|---|
| `obenpaper_rules.py` | The standing rules as data — boards, routes, limits, timezone |
| `validate_queue.py` | Checks `pins_export.json` against those rules |
| `pinterest_publish.py` | Posts due pins (`--dry-run`, `--pin ID`) |
| `cloud_token.py` | Keeps the token alive in Actions; saves each rotation |
| `seed_cloud_token.py` | One-time hand-off of a local token to the cloud |
| `pinterest_auth.py` | One-time OAuth consent (localhost:8085 callback) |
| `pinterest_boards.py` | Lists boards + IDs |
| `pinterest_upload_images.py` | Optional: push images from a local folder via the GitHub API |
| `tests/` | Rule and publisher tests, run on every push |
| `pins_export.json` · `board_map.json` · `posted_ids.json` | Queue, board IDs, record — committed |

Never committed: `config.json`, `token.json`, `images/`.

## Security

- Secrets live only in GitHub repository secrets (cloud) or `config.json` /
  `token.json` (local, gitignored, `token.json` written `0600`).
- The public repo holds only pin images, the queue and these scripts — no
  PDFs, no product files.
- The queue is public once pushed: a pin for an unannounced product reveals
  it. Push those close to their date.
