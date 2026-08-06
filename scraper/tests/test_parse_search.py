import unittest

from scraper.parse_search import _is_sub_document, parse_search_page


SEARCH_PAGE = """<html><body><ul>
  <li class="search-item">
    <h3 class="search-item__title">
      <a class="search-item__clickthrough" href="/publication/policy/ps25-20.pdf">PS25/20: A real policy statement</a>
    </h3>
    <p class="meta-item type">Policy statements</p>
    <p class="meta-item published-date">Published: 20/11/2025</p>
    <p class="meta-item modified-date">Modified: 21/11/2025</p>
  </li>
  <li class="search-item">
    <h3 class="search-item__title">
      <a class="search-item__clickthrough" href="/publication/consultation/cp26-11.pdf">CP 26/11: A consultation with a spaced ref</a>
    </h3>
    <p class="meta-item type">Consultation papers</p>
    <p class="meta-item published-date">Published: 11/06/2026</p>
  </li>
  <li class="search-item">
    <h3 class="search-item__title">
      <a class="search-item__clickthrough" href="/publication/consultation/cp26-6-annex-2.xlsx">CP26/6: Annex 2 Underlying exposures - consumer[xlsx]</a>
    </h3>
    <p class="meta-item type">Consultation papers</p>
    <p class="meta-item published-date">Published: 01/01/2026</p>
  </li>
</ul></body></html>"""


class ParseSearchPageTest(unittest.TestCase):
    def setUp(self):
        self.records = parse_search_page(SEARCH_PAGE, "CP")

    def test_parses_three_items(self):
        self.assertEqual(len(self.records), 3)

    def test_reference_normalised_from_spaced_form(self):
        refs = [r["reference"] for r in self.records]
        self.assertIn("CP26/11", refs)
        self.assertNotIn("CP 26/11", refs)

    def test_dates_parsed(self):
        self.assertEqual(self.records[0]["published_date"], "2025-11-20")

    def test_doc_type_tagged_from_query(self):
        self.assertTrue(all(r["doc_type"] == "CP" for r in self.records))

    def test_annex_record_is_reference_less(self):
        annex = [r for r in self.records if "Annex 2" in r["title"]][0]
        self.assertIsNone(annex["reference"])
        self.assertTrue(annex["landing_url"].endswith(".xlsx"))


class SubDocumentTest(unittest.TestCase):
    def test_annex_title_detected(self):
        self.assertTrue(
            _is_sub_document("CP26/6: Annex 2 exposures", "/publication/cp26-6-annex-2.pdf")
        )

    def test_annex_xlsx_detected(self):
        self.assertTrue(
            _is_sub_document("CP26/6: Annex 2 exposures", "/publication/cp26-6-annex-2.xlsx")
        )

    def test_main_doc_not_sub_document(self):
        self.assertFalse(
            _is_sub_document("CP26/6: Rules for reforming the framework", "/publication/consultation/cp26-6.pdf")
        )


if __name__ == "__main__":
    unittest.main()
