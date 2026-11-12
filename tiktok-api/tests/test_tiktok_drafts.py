import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tiktok_drafts as td  # noqa: E402

MB = td.MB


class ChunkPlan(unittest.TestCase):
    def test_small_file_is_one_chunk(self):
        size, count, ranges = td.chunk_plan(2 * MB + 5)
        self.assertEqual((size, count), (2 * MB + 5, 1))
        self.assertEqual(ranges, [(0, 2 * MB + 4)])

    def test_large_file_last_chunk_takes_remainder(self):
        total = 135 * MB + 7
        size, count, ranges = td.chunk_plan(total)
        self.assertEqual(size, 10 * MB)
        self.assertEqual(count, 13)
        self.assertEqual(ranges[-1][1], total - 1)
        self.assertLessEqual(ranges[-1][1] - ranges[-1][0] + 1, 128 * MB)
        covered = sum(e - s + 1 for s, e in ranges)
        self.assertEqual(covered, total)

    def test_empty_file_refused(self):
        with self.assertRaises(ValueError):
            td.chunk_plan(0)


class Queue(unittest.TestCase):
    Q = [{"id": "a", "file": "x.mp4"}, {"id": "b", "file": "y.mp4"}]

    def test_next_skips_uploaded(self):
        self.assertEqual(td.next_entry(self.Q, ["a"])["id"], "b")

    def test_nothing_left(self):
        self.assertIsNone(td.next_entry(self.Q, ["a", "b"]))

    def test_never_twice_by_id(self):
        with self.assertRaises(SystemExit):
            td.next_entry(self.Q, ["a"], wanted_id="a")

    def test_live_queue_is_valid(self):
        self.assertEqual(td.validate_queue(td.load_json(td.QUEUE_PATH, [])), [])

    def test_duplicate_and_missing_file_flagged(self):
        bad = [{"id": "a", "file": "nope.mp4"}, {"id": "a", "file": "nope.mp4"}]
        problems = td.validate_queue(bad)
        self.assertTrue(any("duplicate" in p for p in problems))
        self.assertTrue(any("not found" in p for p in problems))


class Photos(unittest.TestCase):
    def test_good_carousel_passes(self):
        e = [{"id": "c", "type": "photo", "images": ["https://obenpaper.com/tiktok/a.jpg"]}]
        self.assertEqual(td.validate_queue(e), [])

    def test_png_and_foreign_domain_refused(self):
        e = [{"id": "c", "type": "photo", "images": ["https://example.com/a.png"]}]
        problems = td.validate_queue(e)
        self.assertTrue(any("verified" in p for p in problems))
        self.assertTrue(any("PNG" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
