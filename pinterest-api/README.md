# Obenpaper Pinterest publisher

**Claude makes the pins and the publisher posts them — no action from Luc**
(Luc's decision, 1 Oct 2026). Organic only, through the Pinterest v5 API.

- **App:** `Obenpaper_Scheduler`, app ID `1587406` — **Standard** access.
- **Repo:** `Slimdevils/obenpaper-pins` — public, because Pinterest fetches
  pin images anonymously. Workflow logs are public too: no script prints a
  token, and every secret is masked before anything else runs.

## How it runs

```
every week (Claude, scheduled task)                     every hour (GitHub Actions, :17)
  read catalogue + history                                decrypt token, rotate if due
  write copy, render tiles  ──►  pins_export.json  ──►    validate the queue
  look at every tile             pins/*.png               post ≤ 1 due pin
  validate, commit, push                                  record it in posted_ids.json
```

- **Making pins** — `pin-studio/`. A weekly Claude session follows
  `pin-studio/AGENT.md`: it keeps the queue filled 14 days ahead, one pin
  every two days at 19:00 Zurich, alternating subjects. Copy is written by
  Claude from the facts in `pin-studio/catalogue.json` only; links, boards and
  guardrail lines are filled by `studio.py` from the catalogue, never typed.
- **Posting pins** — `pinterest-api/`. The hourly workflow posts at most one
  due pin per run. A pin more than 24 h late is never posted late.

## Rules enforced on every pin (the queue is refused on any error)

| Rule | Check |
|---|---|
| Organic, plain URLs | no `utm_`, no query string or fragment, https only |
| URLs never guessed | store links must be in `confirmed_links.json` (verbatim from the site's `lib/products.json`); site links must be confirmed routes |
| `macro-split` never pinned | standing exclusion |
| Website boards link to the site | *Free Planner Tools & Quizzes* → `/quiz`, `/tools…`, `/focus`; *Custom & Personalised Planners* → `/made-to-order` |
| FR stays on the FR board | both directions (In Tune FR is not in the catalogue until live) |
| Guardrails | `obenpaper-guardrail-lint` word lists (vendored, `guardrail_lint.py`) on title, description and alt text — off-limits term = error; headline-watch term = error in the title |
| Alternate products, 1–2 day spacing | never the same product twice running, never two pins on one day |
| Fresh pins | a subject at most once every 6 days; a page combination never reused (studio) |
| Pinterest limits | title 100, description/alt 500 — refused, never truncated |
| Board exists | board IDs are filled automatically from the account's board names (spelling-tolerant, never a near match); a missing board blocks only its own pins |

## One-time setup — the only thing Luc does

In your local clone of `obenpaper-pins`:

```
cd pinterest-api
pip install -r requirements.txt
python setup_cloud.py
```

It asks for the app ID and secret (reused from `config.json` if present),
opens Pinterest — click **Give access** — then encrypts everything into
`state/token.enc`, pushes it, and stores the key as the `PINTEREST_KEY`
repository secret (automatically with the GitHub CLI; otherwise it shows the
key once and the page to paste it into). Done.

The redirect URI `http://localhost:8085/callback` must be listed in the
Pinterest app settings (it is already, from the Trial demo).

Run it again only if a workflow run says the token expired or was lost.

### Why there is no other secret

Pinterest rotates the refresh token on every refresh — the old one is spent
at once (30-day access token, 60-day refresh token renewed each time). The
workflow re-encrypts the new token and commits `state/token.enc` before doing
anything else, and refuses to refresh at all if it could not push. It only
refreshes when the access token has under 3 days left, which also commits
roughly monthly and keeps GitHub from pausing the hourly schedule (it pauses
scheduled workflows after 60 days without a commit).

## Files

| Path | Purpose |
|---|---|
| `pin-studio/AGENT.md` | The weekly procedure Claude follows |
| `pin-studio/catalogue.json` | The only subjects that may be pinned, with their facts, accents, board, link |
| `pin-studio/studio.py` | `status` · `slots` · `add batch.json` (fills, renders, validates) |
| `pin-studio/render_tile.py` | 1000×1500 tiles in the house look (§01) |
| `pin-studio/previews/`, `fonts/` | Product page previews (from the site) and the house fonts |
| `pinterest-api/validate_queue.py` | The rules above |
| `pinterest-api/pinterest_publish.py` | Posts due pins (`--dry-run`, `--pin ID`) |
| `pinterest-api/cloud_token.py` | Keeps the token alive, saves each rotation |
| `pinterest-api/setup_cloud.py` | The one-time setup |
| `pinterest-api/confirmed_links.json` | Store URLs a pin may use |
| `pinterest-api/guardrail_lint.py` | Verbatim copy of the guardrail skill's linter |
| `pinterest-api/pins_export.json` · `posted_ids.json` · `board_map.json` | Queue, record, board IDs |
| `pinterest-api/state/` | `token.enc` (encrypted) and `token_meta.json` (expiry dates) |

Manual runs: Actions → *Publish pins* → *Run workflow* → `dry-run`,
`publish` or `list-boards`.

## Keeping it in step with the md

When a product goes live, gets a board, changes name or is retired, the
change is made in a working session with Luc: `catalogue.json` (facts,
board, accent, previews), `confirmed_links.json` (from the site's
`lib/products.json`), and `obenpaper_rules.py` (boards, routes). When the
guardrail skill's word lists change, copy its script over `guardrail_lint.py`
unchanged. The weekly run never edits these itself.
