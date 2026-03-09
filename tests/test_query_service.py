import unittest

from fed_tracker.query import QueryService


class FakeQueryDatabase:
    def get_documents_for_speaker(self, speaker_name, limit=10, before_date=None, within_days=None):
        rows = [
            {
                "id": 1,
                "document_key": "doc_1",
                "speaker_name": speaker_name,
                "title": "Speech A",
                "speech_date": "2026-02-20",
                "document_type": "speech",
                "content_type": "markdown",
                "normalized_text": "Inflation remains elevated. Policy remains restrictive.",
                "source_hash": "hash1",
                "source_metadata": {},
            },
            {
                "id": 2,
                "document_key": "doc_2",
                "speaker_name": speaker_name,
                "title": "Speech B",
                "speech_date": "2026-01-25",
                "document_type": "speech",
                "content_type": "markdown",
                "normalized_text": "Labor market conditions remain tight.",
                "source_hash": "hash2",
                "source_metadata": {},
            },
            {
                "id": 3,
                "document_key": "doc_3",
                "speaker_name": speaker_name,
                "title": "Speech C",
                "speech_date": "2026-01-10",
                "document_type": "speech",
                "content_type": "markdown",
                "normalized_text": "Inflation remains elevated and labor market conditions remain tight.",
                "source_hash": "hash3",
                "source_metadata": {},
            },
        ]
        return rows[:limit]

    def get_fingerprint_for_document(self, document_id, prompt_version=None, model_version=None):
        fingerprints = {
            1: {
                "id": 11,
                "document_id": 1,
                "prompt_version": "v2",
                "model_version": "heuristic-v1",
                "themes": {
                    "INFLATION": {
                        "stance": "concerned",
                        "trajectory": "stable_negative",
                        "emphasis_score": 6,
                        "hedging_level": "light",
                        "key_hedges": ["may"],
                        "confidence": "moderate",
                        "uncertainty": "medium",
                        "evidence": [{"quote": "Inflation remains elevated."}],
                    },
                    "POLICY_STANCE": {
                        "stance": "concerned",
                        "trajectory": "stable",
                        "emphasis_score": 5,
                        "hedging_level": "light",
                        "key_hedges": [],
                        "confidence": "moderate",
                        "uncertainty": "medium",
                        "evidence": [{"quote": "Policy remains restrictive."}],
                    },
                },
                "emergent_themes": [],
                "phrase_signals": [],
                "overall_tone": "measured",
                "uncertainty_notes": [],
                "raw_llm_response": None,
            },
            2: {
                "id": 12,
                "document_id": 2,
                "prompt_version": "v2",
                "model_version": "heuristic-v1",
                "themes": {
                    "LABOR_MARKETS": {
                        "stance": "concerned",
                        "trajectory": "stable_negative",
                        "emphasis_score": 5,
                        "hedging_level": "light",
                        "key_hedges": [],
                        "confidence": "moderate",
                        "uncertainty": "medium",
                        "evidence": [{"quote": "Labor market conditions remain tight."}],
                    }
                },
                "emergent_themes": [],
                "phrase_signals": [],
                "overall_tone": "measured",
                "uncertainty_notes": [],
                "raw_llm_response": None,
            },
            3: {
                "id": 13,
                "document_id": 3,
                "prompt_version": "v2",
                "model_version": "heuristic-v1",
                "themes": {
                    "INFLATION": {
                        "stance": "concerned",
                        "trajectory": "stable_negative",
                        "emphasis_score": 4,
                        "hedging_level": "light",
                        "key_hedges": [],
                        "confidence": "moderate",
                        "uncertainty": "medium",
                        "evidence": [{"quote": "Inflation remains elevated."}],
                    },
                    "LABOR_MARKETS": {
                        "stance": "concerned",
                        "trajectory": "stable_negative",
                        "emphasis_score": 4,
                        "hedging_level": "light",
                        "key_hedges": [],
                        "confidence": "moderate",
                        "uncertainty": "medium",
                        "evidence": [{"quote": "Labor market conditions remain tight."}],
                    },
                },
                "emergent_themes": [],
                "phrase_signals": [],
                "overall_tone": "measured",
                "uncertainty_notes": [],
                "raw_llm_response": None,
            },
        }
        return fingerprints[document_id]

    def get_document_segments(self, document_id):
        return []

    def get_recent_comparisons(self, speaker_name=None, comparison_type=None, limit=10):
        return [
            {
                "comparison_key": "cmp_1",
                "speaker_name": speaker_name,
                "target_document_id": 1,
                "base_document_id": 2,
                "comparison_type": comparison_type or "t_minus_1",
                "window_days": None,
                "theme_changes": [],
                "orphaned_concepts": ["LABOR_MARKETS"],
                "new_themes": [],
                "phrase_anomalies": [],
                "summary": "1 orphaned concept",
                "uncertainty_notes": [],
            }
        ]

    def get_phrase_observations(self, speaker_name, limit=20, min_rarity=None):
        return [
            {
                "phrase_text": "driving in the fog",
                "normalized_phrase": "driving in the fog",
                "semantic_key": "abc123",
                "rarity_score": 3.5,
                "current_count": 2,
                "historical_count": 0,
                "documents": {
                    "speaker_name": speaker_name,
                    "speech_date": "2026-02-01",
                    "title": "Speech A",
                },
            }
        ]

    def get_recent_document_for_speaker(self, speaker_name):
        return self.get_documents_for_speaker(speaker_name)[0]


class QueryServiceTests(unittest.TestCase):
    def test_speaker_timeline_returns_fingerprint_summary(self):
        service = QueryService(database=FakeQueryDatabase())
        payload = service.speaker_timeline("Jerome H. Powell")
        self.assertEqual(payload["count"], 3)
        self.assertIn("INFLATION", payload["timeline"][0]["fingerprint_summary"]["themes"])

    def test_phrase_anomalies_returns_phrase_rows(self):
        service = QueryService(database=FakeQueryDatabase())
        payload = service.phrase_anomalies("Jerome H. Powell")
        self.assertEqual(payload["phrase_anomalies"][0]["phrase_text"], "driving in the fog")

    def test_orphaned_concepts_returns_missing_recent_theme(self):
        service = QueryService(database=FakeQueryDatabase())
        payload = service.orphaned_concepts("Jerome H. Powell", window_days=75)
        self.assertEqual(payload["orphaned_concepts"][0]["theme"], "LABOR_MARKETS")

    def test_theme_drift_returns_paths(self):
        service = QueryService(database=FakeQueryDatabase())
        payload = service.theme_drift("Jerome H. Powell", theme="INFLATION")
        self.assertEqual(payload["theme_drift"][0]["theme"], "INFLATION")
        self.assertEqual(payload["theme_drift"][0]["count"], 2)

    def test_speaker_brief_aggregates_sections(self):
        service = QueryService(database=FakeQueryDatabase())
        payload = service.speaker_brief("Jerome H. Powell", theme="INFLATION")
        self.assertIn("latest_snapshot", payload)
        self.assertIn("orphaned_concepts_75d", payload)
        self.assertIn("theme_drift_24m", payload)

    def test_answer_speaker_question_infers_theme(self):
        service = QueryService(database=FakeQueryDatabase())
        payload = service.answer_speaker_question(
            "Jerome H. Powell",
            "How has Powell's inflation rhetoric shifted over the last two years?",
        )
        self.assertEqual(payload["theme_focus"], "INFLATION")
        self.assertTrue(payload["highlights"])


if __name__ == "__main__":
    unittest.main()
