"""Obenpaper's standing Pinterest rules, as data.

Source of truth is the Obenpaper project-context md (§03 and §07a) and the
`obenpaper-pinterest-pins` skill (references/boards.md). This file mirrors
them so the automatic publisher can refuse a pin that breaks one. When the
md changes, change this file in the same session — never the other way round.
"""

from zoneinfo import ZoneInfo

# Luc is in Geneva; every naive scheduled_at is read as Zurich local time.
TIMEZONE = ZoneInfo("Europe/Zurich")

# --- Boards -----------------------------------------------------------------
# Category key -> EXACT board name on the account (boards.md, eight boards as
# of 18 Aug 2026). board_map.json maps each key to the real board ID; in the
# cloud, a null entry is filled automatically from the board whose name matches
# exactly (case-insensitive) — never by a near match. Add a key here only when
# the board actually exists on the account.
BOARDS = {
    "student_planner": "Student Planner & Study Organization",
    "mindful_drinking": "Mindful Drinking & Sober Curious",
    "cycle_tracking": "Cycle Tracking & Wellness",
    "solo_travel": "Solo Travel Planning & Journals",
    "cycle_fr": "Carnet de cycle & bien-être",  # FR pins stay gated (§07a)
    "free_tools": "Free Planner Tools & Quizzes",
    "custom_planners": "Custom & Personalised Planners",
    "teacher_planner": "Teacher Planner & Lesson Plan Book",
    "scratch": "zz-api-test",  # Trial testing only
}

# --- Destinations -----------------------------------------------------------
SHOP_HOST = "shop.obenpaper.com"
SITE_HOST = "obenpaper.com"

# Confirmed site routes (read off lib/tools.json, 17 Aug 2026). A route not in
# this list is refused until it is confirmed and added here.
SITE_ROUTES = {"/quiz", "/tools", "/focus", "/made-to-order", "/advent"}
TOOL_SLUGS = {
    "compound-interest", "macro-split", "final-score", "cost-per-wear",
    "scale-recipe", "books-per-year", "week-hours", "trip-spend",
    "backlog", "bedtime",
}
# Standing exclusion: a pin strips the safety framing that makes calories
# acceptable on that page. Never pinned — raise it with Luc instead.
NEVER_PIN_SLUGS = {"macro-split"}

# Website-only boards and the routes they accept (boards.md).
SITE_BOARD_ROUTES = {
    "free_tools": lambda path: path in {"/quiz", "/tools", "/focus"}
    or path.startswith("/tools/"),
    "custom_planners": lambda path: path == "/made-to-order",
}

# --- Pacing -----------------------------------------------------------------
MAX_GAP_DAYS = 2            # 1–2 day spacing; a longer gap is only a warning
MISSED_AFTER_HOURS = 24     # a pin this late is skipped, never posted late

# --- Pinterest field limits (fail rather than truncate) ---------------------
LIMITS = {"title": 100, "description": 500, "alt_text": 500}

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")
