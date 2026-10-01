# Weekly pin agent — procedure

Claude runs this every week, unattended, as a scheduled task (Luc's decision,
1 Oct 2026: *Claude makes the pins and posts them, with no action from Luc*).
The hourly GitHub Actions workflow then publishes each pin on its date.

Your job in one run: **keep the queue filled 14 days ahead** with new,
on-brand pins — copy written by you, tiles rendered here and checked by eye.

## 0. Ground rules (standing — never bend them)

- **Organic only.** Never propose or create anything paid.
- **Only subjects in `catalogue.json`**, and **only the facts listed there.**
  Rephrase a fact; never add one (no invented page counts, features, prices,
  outcomes, numbers or claims). If a pin needs a fact that is not there, write
  a different pin.
- **Links, boards and guardrail lines are never written by you** — `studio.py
  add` fills them from the catalogue. A product with no board, or not in the
  catalogue, is not pinned.
- **`macro-split` is never pinned. In Tune FR is not pinned** until its listing
  is live (it is not in the catalogue).
- **Guardrails:** In Check is wellness, never treatment/therapy/cure. In Tune
  is awareness only, never contraception/fertility/conception; "ovulation"
  never in a title. Tools: no targets, no sleep-cycle language, no money
  advice. The validator lints every pin, but write clean copy in the first place.
- **No urgency, no seasons as deadlines** (release calendars were retired).
  Season may inspire an angle, never a "last chance".
- **English copy.** Calm, plain, specific — the Obenpaper voice: say what the
  page does, not how amazing it is. No exclamation marks, no emoji, no hashtags.

## 1. Set up

```bash
git clone --depth 1 https://github.com/slimdevils/obenpaper-pins && cd obenpaper-pins
pip install -r pinterest-api/requirements.txt
```

If the Obenpaper project-context md is available to you (the Obenpaper Project
on claude.ai), read it first: if it shows a product went live, was retired or
changed name since `catalogue.json` was written, **do not pin that product**
and say so in your run summary — the catalogue is updated in a session with
Luc, not by this run.

## 2. See what is needed

```bash
python pin-studio/studio.py status    # history: what ran when, which pages are used
python pin-studio/studio.py slots     # the dates to fill
```

No slots → nothing to do. Stop and report "queue already full".

Also read `pinterest-api/posted_ids.json` and the workflow's latest runs if you
can: if pins are **not** being posted (the publisher is not configured yet, or
runs fail), still fill the queue, and report the problem in one line.

## 3. Plan the batch

One pin per slot. Choose subjects so that:

- **products and site pages alternate** roughly — about 3 product pins for
  every 2 site/tool pins; products carry the sales, site pages carry reach;
- no subject repeats within 6 days (enforced) and **every subject comes round
  before any subject runs a third time**;
- the same board is not used three slots running when another fits.

For each pin pick a **new angle**: a different page, a different reader need
(e.g. Student Planner → exams week, the timetable, the grade tracker). Look
at the subject's preview pages (`pin-studio/previews/<product>/print|tablet/`)
with the Read tool and pick pages that show the angle. `status` lists the
pages already used — never reuse a page combination.

## 4. Write each draft

Write a `batch.json` (outside the repo or deleted afterwards) — a list of:

```json
{
  "subject": "student-planner",
  "scheduled_at": "<a date from slots>",
  "title": "Keyword-first, natural, ≤ 100 chars — what a buyer would search",
  "description": "2–3 sentences, ≤ 500 chars. 1) what it is + format. 2) the page or feature the tile shows. 3) optional soft line: 'Instant download.'",
  "alt_text": "Plain description of what the tile shows, ≤ 500 chars.",
  "tile": {
    "layout": "pages | tablet | type",
    "kicker": "PRODUCT NAME · short label",
    "headline": "3–7 words, the on-image hook — must fit on 2 lines",
    "subline": "short supporting line, often the formats",
    "pages": ["print/03.jpg", "print/06.jpg"]
  }
}
```

- `pages`: 1–2 **print** pages, fanned. `tablet`: exactly 1 **tablet** page in a
  tablet frame. `type`: site pages and tools (no product imagery) — also set
  `card_title`, `card_text` and optionally `badge`; keep the headline and the
  card title different.
- Title ≠ headline: the title is the search phrase, the headline is the hook.
- Pinterest reads the on-image text: the headline should contain the subject's
  core keyword where it reads naturally.

## 5. Add, look, fix

```bash
python pin-studio/studio.py add batch.json
```

It fills links/boards, renders `pins/<id>.png`, and validates the whole queue;
on any error it writes nothing — fix the drafts and run again.

**Then open every new tile with the Read tool and look at it.** Check: text not
cramped or cut, pages clearly visible and relevant to the headline, nothing
misleading. To fix one, edit its `tile` in `pinterest-api/pins_export.json`
and run `python pin-studio/render_tile.py --pin <id>`.

## 6. Ship

```bash
python -m unittest discover -s pinterest-api/tests
python pinterest-api/validate_queue.py
git add pinterest-api/pins_export.json pins/
git commit -m "Queue pins <first date> → <last date>"
git pull --rebase origin main && git push origin HEAD:main
```

The push runs the checks on GitHub; the hourly workflow publishes each pin on
its date. Never post a pin directly yourself, never edit `posted_ids.json`, and
never touch `pinterest-api/state/`.

## 7. Report

End with a short summary in French (Luc's language): the pins added (date ·
subject · headline), anything skipped and why, and any problem seen with
publishing. Nothing else is needed from Luc unless a run says the token expired.
