import unittest

from fed_tracker.comparison import compare_fingerprints
from fed_tracker.extraction import HeuristicFingerprintExtractor
from fed_tracker.normalization import normalize_markdown


class PipelineTests(unittest.TestCase):
    def test_heuristic_extractor_finds_core_themes(self):
        text = """
        Chair Powell said inflation remains elevated, though recent inflation data show some progress.
        The labor market remains strong and job growth has moderated somewhat.
        Policy remains restrictive and the Committee may need to remain patient.
        """
        document = normalize_markdown(text, {"speaker_name": "Jerome H. Powell", "document_type": "speech"})
        extractor = HeuristicFingerprintExtractor()
        fingerprint = extractor.extract(document)

        self.assertIn("INFLATION", fingerprint.themes)
        self.assertIn("LABOR_MARKETS", fingerprint.themes)
        self.assertIn("POLICY_STANCE", fingerprint.themes)
        self.assertTrue(fingerprint.phrase_signals)

    def test_comparison_detects_theme_change(self):
        base_text = """
        Inflation has moderated and price pressures have improved.
        The labor market is balanced and growth is improving.
        """
        target_text = """
        Inflation remains elevated and upside risks persist.
        The labor market remains tight and policy may need to stay restrictive.
        """
        extractor = HeuristicFingerprintExtractor()
        base_doc = normalize_markdown(base_text, {"speaker_name": "Speaker", "document_type": "speech"})
        target_doc = normalize_markdown(target_text, {"speaker_name": "Speaker", "document_type": "speech"})
        base_fp = extractor.extract(base_doc)
        target_fp = extractor.extract(target_doc, historical_texts=[base_doc.normalized_text])

        comparison = compare_fingerprints(base_fp, target_fp, context_fingerprints=[base_fp])
        self.assertTrue(comparison.theme_changes or comparison.new_themes)


if __name__ == "__main__":
    unittest.main()
