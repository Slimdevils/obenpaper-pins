"""The pin studio: every catalogue subject is pinnable and every layout renders."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "pin-studio"))
sys.path.insert(0, os.path.dirname(HERE))

from obenpaper_rules import BOARDS, SITE_HOST  # noqa: E402
from render_tile import STUDIO, load_catalogue, render  # noqa: E402
from guardrail_lint import WORDLISTS  # noqa: E402
from validate_queue import check_link, confirmed_shop_links  # noqa: E402


class Catalogue(unittest.TestCase):
    def test_every_subject_is_pinnable(self):
        shop = confirmed_shop_links()
        for key, s in load_catalogue().items():
            with self.subTest(key):
                self.assertIn(s["board"], BOARDS)
                self.assertNotEqual(s["board"], "cycle_fr")
                self.assertIn(s["guardrail"], WORDLISTS)
                self.assertEqual(check_link({"link": s["link"]}, s["board"]), [])
                if SITE_HOST not in s["link"].split("/")[2] or "shop." in s["link"]:
                    self.assertIn(s["link"], shop)
                self.assertNotIn("macro-split", s["link"])
                if s.get("previews"):
                    self.assertTrue(os.path.isdir(os.path.join(STUDIO, s["previews"])))


class Render(unittest.TestCase):
    def test_each_layout(self):
        cat = load_catalogue()
        cases = [
            ("student-planner", {"layout": "pages", "headline": "Exams and grades in one place",
                                 "subline": "Tablet, A4 and US Letter", "pages": ["print/08.jpg", "print/09.jpg"]}),
            ("in-session", {"layout": "tablet", "headline": "A plan book for every term",
                            "pages": ["tablet/09.jpg"]}),
            ("quiz", {"layout": "type", "headline": "Which planner fits you?",
                      "card_title": "Find your planner", "card_text": "A free quiz."}),
        ]
        out = tempfile.mkdtemp()
        for key, tile in cases:
            with self.subTest(key):
                path = render({"tile": tile}, cat[key], os.path.join(out, f"{key}.png"))
                self.assertTrue(os.path.getsize(path) > 10_000)

    def test_three_line_headline_refused(self):
        with self.assertRaises(ValueError):
            render({"tile": {"layout": "type", "headline": "A very long headline that will never fit on two lines at any size we allow here"}},
                   load_catalogue()["quiz"], os.path.join(tempfile.mkdtemp(), "x.png"))


if __name__ == "__main__":
    unittest.main()
