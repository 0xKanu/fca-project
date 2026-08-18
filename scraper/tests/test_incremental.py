import os
import tempfile
import unittest

from classifiers.data_utils import append_predictions, load_predictions, read_stems_file
from scraper.index import _dedupe_key, _pub_date, select_incremental


def rec(ref, date, url="https://www.fca.org.uk/x"):
    return {
        "title": f"{ref}: doc",
        "reference": ref,
        "doc_type": "PS",
        "published_date": date,
        "landing_url": url,
    }


class IncrementalSelectionTest(unittest.TestCase):
    def test_no_prior_index_treats_everything_as_new(self):
        delta = select_incremental([rec("PS25/1", "2025-01-01"), rec("PS25/2", "2025-01-02")], [])
        self.assertEqual(len(delta), 2)

    def test_re_scrape_of_same_set_is_empty(self):
        existing = [rec("PS25/1", "2025-01-01"), rec("PS25/2", "2025-01-02")]
        self.assertEqual(select_incremental(existing, existing), [])

    def test_new_ref_on_same_date_is_new(self):
        existing = [rec("PS25/1", "2025-01-02")]
        fresh = [rec("PS25/1", "2025-01-02"), rec("PS25/2", "2025-01-02")]
        delta = select_incremental(fresh, existing)
        self.assertEqual([d["reference"] for d in delta], ["PS25/2"])

    def test_newer_date_with_new_ref_is_new(self):
        existing = [rec("PS25/1", "2025-01-02")]
        fresh = [rec("PS26/1", "2026-01-01")]
        self.assertEqual(len(select_incremental(fresh, existing)), 1)

    def test_seen_ref_re_published_newer_date_is_new(self):
        existing = [rec("PS25/1", "2025-01-02")]
        fresh = [rec("PS25/1", "2026-01-01")]
        self.assertEqual(len(select_incremental(fresh, existing)), 1)

    def test_seen_ref_older_date_is_not_new(self):
        existing = [rec("PS25/1", "2025-06-01")]
        fresh = [rec("PS25/1", "2025-01-01")]
        self.assertEqual(select_incremental(fresh, existing), [])

    def test_null_ref_dedupes_on_landing_url(self):
        a = {"title": "doc", "reference": None, "published_date": "2025-01-01",
             "landing_url": "https://www.fca.org.uk/same"}
        b = {"title": "doc", "reference": None, "published_date": "2025-01-01",
             "landing_url": "https://www.fca.org.uk/same"}
        self.assertEqual(select_incremental([a, b], []), [a])

    def test_dates_are_normalised_before_comparison(self):
        existing = [rec("PS25/1", "2025-01-02")]
        # same calendar day, different timestamp string -> still equal -> not new
        fresh = [dict(rec("PS25/1", "2025-01-02"), published_date="2025-01-02T08:00:00")]
        self.assertEqual(select_incremental(fresh, existing), [])

    def test_pub_date_normalisation(self):
        self.assertEqual(_pub_date(rec("X", "2025-01-02")), __import__("datetime").date(2025, 1, 2))
        self.assertIsNone(_pub_date({"published_date": None}))

    def test_dedupe_key_falls_back_to_url(self):
        self.assertEqual(_dedupe_key(rec("PS25/1", "2025-01-01")), ("ref", "PS25/1"))
        self.assertEqual(_dedupe_key({"reference": None, "landing_url": "u"}), ("url", "u"))


class AppendPredictionsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.csv = os.path.join(self.dir, "m.csv")
        from classifiers import data_utils

        self._orig = data_utils.PRED_DIR
        data_utils.PRED_DIR = __import__("pathlib").Path(self.dir)
        append_predictions.__globals__["PRED_DIR"] = __import__("pathlib").Path(self.dir)

    def tearDown(self):
        from classifiers import data_utils

        data_utils.PRED_DIR = self._orig

    def test_append_keeps_existing_and_adds_new(self):
        append_predictions("m", {"a": "amendment"}, {"a": 0.9})
        append_predictions("m", {"a": "WRONG", "b": "consultation"}, {"a": 0.1, "b": 0.8})
        preds = load_predictions("m")
        self.assertEqual(preds["a"], "amendment")  # existing preserved
        self.assertEqual(preds["b"], "consultation")  # new appended

    def test_append_is_idempotent_on_re_run(self):
        append_predictions("m", {"a": "amendment"}, {"a": 0.9})
        append_predictions("m", {"a": "amendment"}, {"a": 0.9})
        preds = load_predictions("m")
        self.assertEqual(len(preds), 1)
        self.assertEqual(preds["a"], "amendment")

    def test_read_stems_file_ignores_blanks_and_comments(self):
        path = os.path.join(self.dir, "s.txt")
        with open(path, "w") as f:
            f.write("# comment\n\nPS23_5\n PS23_13 \n")
        self.assertEqual(read_stems_file(path), ["PS23_5", "PS23_13"])


if __name__ == "__main__":
    unittest.main()