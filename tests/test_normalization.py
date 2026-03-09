import unittest
from pathlib import Path

from fed_tracker.models import DocumentType
from fed_tracker.normalization import (
    _extract_date,
    _extract_speaker,
    _extract_title_for_site,
    _html_to_text,
    _html_to_text_for_site,
    _refine_fed_text,
    _site_config,
    _suppress_boilerplate_blocks,
)


class NormalizationTests(unittest.TestCase):
    def _fixture_text(self, name: str) -> bytes:
        return (Path(__file__).parent / "fixtures" / name).read_bytes()

    def test_fed_refinement_removes_navigation_noise(self):
        html = b"""
        <html>
          <body>
            <main>
              <h1>Test Speech</h1>
              <p>Federal Reserve Board</p>
              <p>January 10, 2026</p>
              <p>Thank you for the invitation to speak today.</p>
              <p>Inflation remains elevated and the labor market is strong.</p>
              <p>Last Update: January 11, 2026</p>
              <p>Back to Top</p>
            </main>
          </body>
        </html>
        """
        text, _soup = _html_to_text(html)
        refined = _refine_fed_text(text, "Test Speech")
        self.assertIn("Inflation remains elevated", refined)
        self.assertNotIn("Last Update", refined)
        self.assertNotIn("Federal Reserve Board", refined)

    def test_board_site_specific_selectors_extract_core_fields(self):
        html = self._fixture_text("federalreserve_board_live_sample.html")
        config = _site_config("https://www.federalreserve.gov/newsevents/speech/example.htm")
        text, soup = _html_to_text_for_site(html, selectors=config["content_selectors"])
        title = _extract_title_for_site(soup, None, selectors=config["title_selectors"])
        speaker = _extract_speaker(text, soup, selectors=config["speaker_selectors"])
        speech_date = _extract_date(text, soup, selectors=config["date_selectors"])

        self.assertEqual(title, "AI and the Economy")
        self.assertEqual(speaker, "Vice Chair Philip N. Jefferson")
        self.assertEqual(str(speech_date), "2025-11-07")
        self.assertIn("artificial intelligence", text.lower())

    def test_new_york_fed_site_specific_selectors_extract_body(self):
        html = self._fixture_text("newyorkfed_live_sample.html")
        config = _site_config("https://www.newyorkfed.org/newsevents/speeches/2026/wil260303")
        text, soup = _html_to_text_for_site(html, selectors=config["content_selectors"])
        title = _extract_title_for_site(soup, None, selectors=config["title_selectors"])
        speaker = _extract_speaker(text, soup, selectors=config["speaker_selectors"])
        speech_date = _extract_date(text, soup, selectors=config["date_selectors"])

        self.assertEqual(title, "Two Sides of a Coin")
        self.assertIn("John C. Williams", speaker)
        self.assertEqual(str(speech_date), "2026-03-03")
        self.assertIn("maximum employment and price stability", text)

    def test_dallas_fed_site_specific_selectors_extract_body(self):
        html = self._fixture_text("dallasfed_live_sample.html")
        config = _site_config("https://www.dallasfed.org/news/speeches/logan/2026/lkl260210")
        text, soup = _html_to_text_for_site(html, selectors=config["content_selectors"])
        title = _extract_title_for_site(soup, None, selectors=config["title_selectors"])
        speaker = _extract_speaker(text, soup, selectors=config["speaker_selectors"])
        speech_date = _extract_date(text, soup, selectors=config["date_selectors"])

        self.assertEqual(title, "Outlook for the economy and monetary policy")
        self.assertEqual(speaker, "Lorie Logan")
        self.assertEqual(str(speech_date), "2026-02-10")
        self.assertIn("inflation still elevated", text.lower())

    def test_board_press_release_fixture_extracts_and_suppresses_boilerplate(self):
        html = self._fixture_text("federalreserve_press_release_live_sample.html")
        config = _site_config("https://www.federalreserve.gov/newsevents/pressreleases/monetary20250129a.htm")
        text, soup = _html_to_text_for_site(html, selectors=config["content_selectors"])
        title = _extract_title_for_site(soup, None, selectors=config["title_selectors"])
        speech_date = _extract_date(text, soup, selectors=config["date_selectors"])
        suppressed = _suppress_boilerplate_blocks(text, DocumentType.STATEMENT, source="Board of Governors")

        self.assertEqual(title, "Federal Reserve issues FOMC statement")
        self.assertEqual(str(speech_date), "2025-01-29")
        self.assertIn("Inflation remains somewhat elevated.", text)
        self.assertNotIn("The Committee seeks to achieve maximum employment", suppressed)

    def test_press_release_boilerplate_is_suppressed(self):
        text = """
        Information received since the Federal Open Market Committee met indicates that economic activity has continued to expand at a solid pace.

        The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run.

        Policymakers noted that inflation remains elevated and housing services inflation has been sticky.
        """.strip()
        suppressed = _suppress_boilerplate_blocks(text, DocumentType.PRESS_RELEASE)
        self.assertNotIn("The Committee seeks to achieve maximum employment", suppressed)
        self.assertIn("inflation remains elevated", suppressed.lower())

    def test_press_conference_boilerplate_is_suppressed(self):
        text = """
        Thank you. I'm happy to take your questions.

        Let me say a few words about the economy before we begin.

        Labor market conditions have softened modestly.
        """.strip()
        suppressed = _suppress_boilerplate_blocks(text, DocumentType.PRESS_CONFERENCE)
        self.assertNotIn("happy to take your questions", suppressed.lower())
        self.assertIn("Labor market conditions have softened", suppressed)

    def test_source_override_boilerplate_is_suppressed(self):
        text = """
        For media inquiries, call 202-452-2955.

        Inflation remains elevated.
        """.strip()
        suppressed = _suppress_boilerplate_blocks(
            text,
            DocumentType.PRESS_RELEASE,
            source="Board of Governors",
        )
        self.assertNotIn("media inquiries", suppressed.lower())
        self.assertIn("Inflation remains elevated.", suppressed)


if __name__ == "__main__":
    unittest.main()
