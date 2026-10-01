"""Tests for the queue rules and the publisher. Run from pinterest-api/:

    python -m unittest discover -s tests -v

No network: Pinterest and image fetches are replaced with fakes.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pinterest_publish  # noqa: E402
import validate_queue  # noqa: E402
from obenpaper_rules import BOARDS, TIMEZONE  # noqa: E402
from validate_queue import validate  # noqa: E402

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=TIMEZONE)
BOARD_MAP = {key: f"id-{key}" for key in BOARDS}


class FixedNow(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def pin(pid, product, days, **over):
    base = {
        "id": pid,
        "product": product,
        "category": "student_planner",
        "image_file": f"{pid}.png",
        "title": "Dated Student Planner Printable",
        "description": "A dated academic planner, printable or for tablet.",
        "alt_text": "A weekly spread with class slots.",
        "link": "https://shop.obenpaper.com/b/YpUmC",
        "link_confirmed": True,
        "scheduled_at": (NOW + timedelta(days=days)).replace(tzinfo=None).isoformat(),
    }
    base.update(over)
    return base


def errors_for(pins, posted=()):
    errors, _, _ = validate(pins, BOARD_MAP, set(posted), NOW)
    return errors


class LinkRules(unittest.TestCase):
    def test_clean_pin_passes(self):
        self.assertEqual(errors_for([pin("A", "Student Planner", 1)]), [])

    def test_utm_refused(self):
        p = pin("A", "Student Planner", 1, link="https://shop.obenpaper.com/b/YpUmC?utm_source=pinterest")
        self.assertTrue(any("UTM" in e for e in errors_for([p])))

    def test_any_query_string_refused(self):
        p = pin("A", "Student Planner", 1, link="https://shop.obenpaper.com/b/YpUmC?ref=x")
        self.assertTrue(any("query string" in e for e in errors_for([p])))

    def test_foreign_host_refused(self):
        p = pin("A", "Student Planner", 1, link="https://www.etsy.com/listing/123")
        self.assertTrue(any("host" in e for e in errors_for([p])))

    def test_unconfirmed_link_refused(self):
        p = pin("A", "Student Planner", 1, link_confirmed=False)
        self.assertTrue(any("link_confirmed" in e for e in errors_for([p])))

    def test_macro_split_never_pinned(self):
        p = pin("A", "Tools", 1, category="free_tools", link="https://obenpaper.com/tools/macro-split")
        self.assertTrue(any("standing exclusion" in e for e in errors_for([p])))

    def test_unknown_route_refused(self):
        p = pin("A", "Tools", 1, category="free_tools", link="https://obenpaper.com/pricing")
        self.assertTrue(any("not a confirmed site route" in e for e in errors_for([p])))

    def test_site_board_cannot_link_to_store(self):
        p = pin("A", "Quiz", 1, category="free_tools")
        self.assertTrue(any("website board" in e for e in errors_for([p])))

    def test_made_to_order_only_on_its_board(self):
        p = pin("A", "Made to Order", 1, category="free_tools", link="https://obenpaper.com/made-to-order")
        self.assertTrue(any("does not belong" in e for e in errors_for([p])))

    def test_tool_pin_on_product_board_ok(self):
        p = pin("A", "Final Score tool", 1, link="https://obenpaper.com/tools/final-score")
        self.assertEqual(errors_for([p]), [])

    def test_trailing_slash_refused(self):
        p = pin("A", "Student Planner", 1, link="https://shop.obenpaper.com/b/YpUmC/")
        self.assertTrue(any("trailing slash" in e for e in errors_for([p])))


class BoardAndCopyRules(unittest.TestCase):
    def test_unmapped_board_refused(self):
        p = pin("A", "Student Planner", 1)
        errors, _, _ = validate([p], {**BOARD_MAP, "student_planner": None}, set(), NOW)
        self.assertTrue(any("no board ID" in e for e in errors))

    def test_fr_product_only_on_fr_board(self):
        p = pin("A", "In Tune FR", 1, category="cycle_tracking")
        self.assertTrue(any("FR board only" in e for e in errors_for([p])))

    def test_fr_board_only_takes_fr(self):
        p = pin("A", "In Tune", 1, category="cycle_fr")
        self.assertTrue(any("only takes FR" in e for e in errors_for([p])))

    def test_title_over_limit_refused_not_truncated(self):
        p = pin("A", "Student Planner", 1, title="x" * 101)
        self.assertTrue(any("title is 101" in e for e in errors_for([p])))

    def test_video_refused(self):
        p = pin("A", "In Focus", 1, image_file="day.mp4")
        self.assertTrue(any("video" in e for e in errors_for([p])))

    def test_duplicate_ids(self):
        errs = errors_for([pin("A", "Student Planner", 1), pin("A", "In Session", 3)])
        self.assertTrue(any("duplicate" in e for e in errs))


class Pacing(unittest.TestCase):
    def test_same_product_back_to_back_refused(self):
        errs = errors_for([pin("A", "Student Planner", 1), pin("B", "Student Planner", 2)])
        self.assertTrue(any("same product" in e for e in errs))

    def test_two_on_one_day_refused(self):
        a = pin("A", "Student Planner", 1)
        b = pin("B", "In Session", 1, scheduled_at=(NOW + timedelta(days=1, hours=3)).replace(tzinfo=None).isoformat())
        self.assertTrue(any("one pin per day" in e for e in errors_for([a, b])))

    def test_alternating_daily_ok(self):
        pins = [pin("A", "Student Planner", 1), pin("B", "In Session", 2), pin("C", "Student Planner", 4)]
        errors, warnings, _ = validate(pins, BOARD_MAP, set(), NOW)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_long_gap_is_only_a_warning(self):
        errors, warnings, _ = validate(
            [pin("A", "Student Planner", 1), pin("B", "In Session", 6)], BOARD_MAP, set(), NOW)
        self.assertEqual(errors, [])
        self.assertTrue(any("gap" in w for w in warnings))

    def test_missed_pin_flagged_not_error(self):
        errors, warnings, missed = validate([pin("A", "Student Planner", -2)], BOARD_MAP, set(), NOW)
        self.assertEqual(errors, [])
        self.assertEqual(missed, {"A"})

    def test_posted_pin_not_missed(self):
        _, _, missed = validate([pin("A", "Student Planner", -2)], BOARD_MAP, {"A"}, NOW)
        self.assertEqual(missed, set())

    def test_naive_time_is_zurich(self):
        when = validate_queue.parse_when("2026-10-12T09:00:00")
        self.assertEqual(when.utcoffset(), timedelta(hours=2))  # CEST


class Publisher(unittest.TestCase):
    """End to end with fake Pinterest: due pin posts once, then never again."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {
            name: os.path.join(self.tmp, name)
            for name in ("pins_export.json", "board_map.json", "posted_ids.json")
        }
        pins = [
            pin("DUE", "Student Planner", -0.1, image_url="https://raw.example/due.png"),
            pin("LATE", "In Session", -3, image_url="https://raw.example/late.png"),
            pin("LATER", "In Session", 1, image_url="https://raw.example/later.png"),
        ]
        # LATE (missed) sits before DUE in time; keep products alternating.
        with open(self.paths["pins_export.json"], "w") as fh:
            json.dump(pins, fh)
        with open(self.paths["board_map.json"], "w") as fh:
            json.dump(BOARD_MAP, fh)
        self.patches = [
            mock.patch.object(validate_queue, "PINS_PATH", self.paths["pins_export.json"]),
            mock.patch.object(validate_queue, "MAP_PATH", self.paths["board_map.json"]),
            mock.patch.object(validate_queue, "POSTED_PATH", self.paths["posted_ids.json"]),
            mock.patch.object(pinterest_publish, "POSTED_PATH", self.paths["posted_ids.json"]),
            mock.patch.object(pinterest_publish, "load_config",
                              return_value={"max_posts_per_run": 1, "github_owner": "o",
                                            "github_repo": "r", "github_branch": "main"}),
            mock.patch.object(pinterest_publish, "auth_headers", return_value={"Authorization": "Bearer x"}),
            mock.patch.object(pinterest_publish, "image_reachable", return_value=True),
            mock.patch.object(pinterest_publish, "datetime", FixedNow),
        ]
        for p in self.patches:
            p.start()
        self.sent = []

        def fake_post(url, headers, json, timeout):
            self.sent.append(json)
            resp = mock.Mock(status_code=201)
            resp.json.return_value = {"id": f"pin{len(self.sent)}"}
            return resp

        self.post = mock.patch.object(pinterest_publish.requests, "post", side_effect=fake_post)
        self.post.start()

    def tearDown(self):
        self.post.stop()
        for p in self.patches:
            p.stop()

    def run_publisher(self, *args):
        with mock.patch.object(sys, "argv", ["pinterest_publish.py", *args]):
            return pinterest_publish.main()

    def test_due_pin_posts_once_and_missed_never(self):
        self.assertEqual(self.run_publisher(), 0)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["board_id"], "id-student_planner")
        self.assertEqual(self.sent[0]["link"], "https://shop.obenpaper.com/b/YpUmC")
        self.assertNotIn("utm", json.dumps(self.sent[0]))

        self.assertEqual(self.run_publisher(), 0)   # second run: nothing new
        self.assertEqual(len(self.sent), 1)
        with open(self.paths["posted_ids.json"]) as fh:
            self.assertEqual([e["pin"] for e in json.load(fh)], ["DUE"])

    def test_dry_run_sends_nothing(self):
        self.assertEqual(self.run_publisher("--dry-run"), 0)
        self.assertEqual(self.sent, [])

    def test_broken_queue_publishes_nothing(self):
        with open(self.paths["pins_export.json"]) as fh:
            pins = json.load(fh)
        pins[0]["link"] += "?utm_source=x"
        with open(self.paths["pins_export.json"], "w") as fh:
            json.dump(pins, fh)
        self.assertEqual(self.run_publisher(), 1)
        self.assertEqual(self.sent, [])

    def test_single_pin_cannot_be_posted_twice(self):
        self.run_publisher()
        with self.assertRaises(SystemExit):
            self.run_publisher("--pin", "DUE")


if __name__ == "__main__":
    unittest.main()
