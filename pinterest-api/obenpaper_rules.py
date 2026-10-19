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
# Category key -> board name AS IT EXISTS ON THE ACCOUNT, read through the API
# on 19 Oct 2026 (pinterest-api/state/account_boards.json). The account is
# organised by collection, not by the per-niche boards boards.md listed in
# August — those (Mindful Drinking, Cycle Tracking, Solo Travel, the FR board)
# do not exist on it. board_map.json maps each key to the board's ID; in the
# cloud a null entry is filled from the name (spelling-tolerant, never a near
# match). Add a key only when the board actually exists on the account.
BOARDS = {
    "student_planner": "Student Planner & Study Organization",
    "teacher_planner": "Teacher Planner & Lesson Plan Book",
    "free_tools": "Free Planner Tools & Quizzes",
    "custom_planners": "Custom & Personalised Planners",
    "self_care": "Self Care & Wellness",
    "travel": "Travel",
    "planners": "Planners & Productivity",
    "home": "Home & Lifestyle",
    "hobbies": "Hobbies & Downtime",
    "work_finance": "Work & Finance",
    "scratch": "zz-api-test",  # Trial testing only
}

# There is no French board on the account: an FR product cannot be pinned
# until one exists (In Tune FR is gated on its listing anyway, §07a).
FR_BOARD = None


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
