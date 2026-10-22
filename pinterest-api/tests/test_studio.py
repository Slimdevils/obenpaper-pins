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


class Video(unittest.TestCase):
    """The video spec is checked without Node; the render runs only where
    `npm ci --prefix pin-studio/video` has been done (not on GitHub)."""

    def pages(self, key, names):
        s = load_catalogue()[key]
        return [os.path.join(STUDIO, s["previews"], n) for n in names]

    def test_spec_fits_like_a_tile(self):
        from video_spec import build_spec
        s = load_catalogue()["in-check"]
        spec = build_spec("pin", s["accent"], "In Check", "Notice the urge, then let it pass",
                          "Tablet, A4 and US Letter",
                          self.pages("in-check", ["tablet/01.jpg", "tablet/03.jpg", "tablet/05.jpg"]))
        layout = spec["props"]["layout"]
        self.assertLessEqual(len(layout["headline"]["lines"]), 2)
        self.assertEqual(spec["props"]["edition"], "tablet")
        self.assertGreater(layout["media"]["h"], 500)

    def test_every_format_lays_out(self):
        from video_spec import FORMATS, build_spec
        s = load_catalogue()["in-check"]
        for fmt in FORMATS:
            with self.subTest(fmt):
                build_spec(fmt, s["accent"], "In Check", "A gentle journal for drinking less",
                           "Tablet, A4 and US Letter",
                           self.pages("in-check", ["print/01.jpg", "print/02.jpg", "print/03.jpg"]), "")

    def test_too_few_pages_refused(self):
        from video_spec import build_spec
        s = load_catalogue()["in-check"]
        with self.assertRaises(ValueError):
            build_spec("pin", s["accent"], "", "Two pages only", "", self.pages("in-check", ["print/01.jpg", "print/02.jpg"]))

    def test_mixed_editions_refused(self):
        from video_spec import build_spec
        s = load_catalogue()["in-check"]
        with self.assertRaises(ValueError):
            build_spec("pin", s["accent"], "", "Mixed pages", "",
                       self.pages("in-check", ["print/01.jpg", "tablet/02.jpg", "print/03.jpg"]))

    @unittest.skipUnless(os.path.isdir(os.path.join(STUDIO, "video", "node_modules")), "video renderer not installed")
    def test_render_video_pin(self):
        from video_spec import render_pin_video
        out = tempfile.mkdtemp()
        pin = {"tile": {"layout": "video", "kicker": "In Check", "headline": "Notice the urge",
                        "pages": ["tablet/01.jpg", "tablet/02.jpg", "tablet/03.jpg"]}}
        render_pin_video(pin, load_catalogue()["in-check"], os.path.join(out, "v.mp4"), os.path.join(out, "v.png"))
        self.assertGreater(os.path.getsize(os.path.join(out, "v.mp4")), 100_000)
        self.assertGreater(os.path.getsize(os.path.join(out, "v.png")), 10_000)


if __name__ == "__main__":
    unittest.main()
