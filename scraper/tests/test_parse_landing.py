import unittest

from scraper.parse_landing import extract_primary_pdf, external_read_link

LANDING = """<html><body>
  <a href="/publication/policy/ps25-20.pdf">Read PS25/20 (PDF)</a>
  <a href="/publication/policy/ps25-20-annex-a.pdf">Annex A</a>
  <a href="https://www.bankofengland.co.uk/prudential-regulation/publication/2025/january/ps17-25">Read the PRA PS17/25</a>
</body></html>"""


class ExtractPrimaryPdfTest(unittest.TestCase):
    def test_prefers_reference_titled_link(self):
        url = extract_primary_pdf(LANDING, "https://www.fca.org.uk/article", {"reference": "PS25/20", "doc_type": "PS"})
        self.assertIn("ps25-20.pdf", url)
        self.assertNotIn("annex", url)

    def test_external_link_ignored_for_local_pdf(self):
        url = extract_primary_pdf(LANDING, "https://www.fca.org.uk/article", {"reference": "PS25/20", "doc_type": "PS"})
        self.assertIn("fca.org.uk", url)

    def test_exclude_appendix_drops_annex(self):
        url = extract_primary_pdf(LANDING, "https://www.fca.org.uk/a", {"reference": "PS25/20", "doc_type": "PS"}, exclude_appendix=True)
        self.assertIn("ps25-20.pdf", url)


class ExternalReadLinkTest(unittest.TestCase):
    def test_finds_external_read_anchor(self):
        url = external_read_link(LANDING, "https://www.fca.org.uk/a", {"reference": "PS24/13"})
        self.assertIn("bankofengland.co.uk", url)


if __name__ == "__main__":
    unittest.main()
