import unittest

from scraper.extract import html_to_text
from scraper.sample import allocate
from collections import Counter


class ExtractHtmlTextTest(unittest.TestCase):
    def test_noise_removed_and_text_collapsed(self):
        html = """
        <html><body>
          <nav>Skip to content | Home</nav>
          <h1>Title</h1>
          <p>First   paragraph.</p>
          <script>var x = 1;</script>
          <footer>Privacy | Cookies</footer>
        </body></html>
        """
        text = html_to_text(html)
        self.assertIn("Title", text)
        self.assertIn("First paragraph.", text)
        self.assertNotIn("Skip to content", text)
        self.assertNotIn("Privacy", text)
        self.assertNotIn("var x", text)
        self.assertNotIn("  ", text)


class AllocateTest(unittest.TestCase):
    def test_floor_of_one_per_stratum(self):
        counts = Counter({"a": 1000, "b": 1})
        result = allocate(counts, 5)
        self.assertGreaterEqual(result["b"], 1)

    def test_total_close_to_target(self):
        counts = Counter({"a": 60, "b": 30, "c": 10})
        result = allocate(counts, 15)
        self.assertEqual(sum(result.values()), 15)
        self.assertGreaterEqual(result["c"], 1)


if __name__ == "__main__":
    unittest.main()
