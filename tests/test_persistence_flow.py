import unittest

from fed_tracker.extraction import HeuristicFingerprintExtractor
from fed_tracker.pipeline import AnalysisPipeline


class FakeDatabase:
    def __init__(self):
        self.next_id = 1
        self.source_documents = {}
        self.documents = {}
        self.documents_by_key = {}
        self.document_segments = {}
        self.analysis_runs = {}
        self.fingerprints = {}
        self.comparisons = {}

    def _id(self):
        value = self.next_id
        self.next_id += 1
        return value

    def insert_source_document(self, **payload):
        new_id = self._id()
        self.source_documents[new_id] = {"id": new_id, **payload}
        return new_id

    def source_document_exists(self, source_url: str) -> bool:
        return any(row.get("source_url") == source_url for row in self.source_documents.values())

    def insert_document(self, document, source_document_id=None, **_kwargs):
        new_id = self._id()
        row = {
            "id": new_id,
            "document_key": document.document_id,
            "source_document_id": source_document_id,
            "speaker_name": document.speaker_name,
            "title": document.title,
            "speech_date": document.speech_date.isoformat() if document.speech_date else None,
            "document_type": document.document_type.value,
            "source": document.source,
            "content_type": document.content_type.value,
            "normalized_text": document.normalized_text,
            "raw_content": document.raw_content,
            "raw_markdown": document.raw_markdown,
            "source_hash": document.source_hash,
            "source_metadata": document.source_metadata,
        }
        self.documents[new_id] = row
        self.documents_by_key[document.document_id] = row
        self.document_segments[new_id] = [
            {
                "segment_index": segment.segment_index,
                "speaker_name": segment.speaker_name,
                "segment_type": segment.segment_type.value,
                "text": segment.text,
            }
            for segment in document.segments
        ]
        return new_id

    def insert_analysis_run(self, run):
        new_id = self._id()
        self.analysis_runs[new_id] = {"id": new_id, **run.model_dump(mode="json")}
        return new_id

    def insert_fingerprint(self, fingerprint, document_id, analysis_run_id=None):
        new_id = self._id()
        self.fingerprints[document_id] = {
            "id": new_id,
            "document_id": document_id,
            "analysis_run_id": analysis_run_id,
            "prompt_version": fingerprint.prompt_version,
            "model_version": fingerprint.model_version,
            "themes": {name: value.model_dump(mode="json") for name, value in fingerprint.themes.items()},
            "emergent_themes": fingerprint.emergent_themes,
            "phrase_signals": [signal.model_dump(mode="json") for signal in fingerprint.phrase_signals],
            "overall_tone": fingerprint.overall_tone,
            "uncertainty_notes": fingerprint.uncertainty_notes,
            "raw_llm_response": fingerprint.raw_llm_response,
        }
        return new_id

    def insert_comparison_result(self, comparison, **kwargs):
        new_id = self._id()
        self.comparisons[new_id] = {
            "id": new_id,
            "comparison_key": comparison.comparison_id,
            "speaker_name": comparison.speaker_name,
            "target_document_id": kwargs.get("target_document_id"),
            "base_document_id": kwargs.get("base_document_id"),
            "comparison_type": comparison.comparison_type.value,
            "window_days": comparison.window_days,
            "theme_changes": [change.model_dump(mode="json") for change in comparison.theme_changes],
            "orphaned_concepts": comparison.orphaned_concepts,
            "new_themes": comparison.new_themes,
            "phrase_anomalies": [signal.model_dump(mode="json") for signal in comparison.phrase_anomalies],
            "summary": comparison.summary,
            "uncertainty_notes": comparison.uncertainty_notes,
        }
        return new_id

    def get_documents_for_speaker(self, speaker_name, before_date=None, within_days=None, limit=100):
        rows = [row for row in self.documents.values() if row.get("speaker_name") == speaker_name]
        if before_date:
            rows = [row for row in rows if row.get("speech_date") and row["speech_date"] < before_date.isoformat()]
        rows.sort(key=lambda row: row.get("speech_date") or "", reverse=True)
        return rows[:limit]

    def get_fingerprint_for_document(self, document_id, prompt_version=None, model_version=None):
        return self.fingerprints.get(document_id)

    def get_document_segments(self, document_id):
        return self.document_segments.get(document_id, [])

    def get_document_by_key(self, document_key):
        return self.documents_by_key.get(document_key)

    def get_recent_document_for_speaker(self, speaker_name):
        rows = self.get_documents_for_speaker(speaker_name, limit=1)
        return rows[0] if rows else None

    def get_recent_comparisons(self, speaker_name=None, comparison_type=None, limit=20):
        rows = list(self.comparisons.values())
        if speaker_name:
            rows = [row for row in rows if row.get("speaker_name") == speaker_name]
        if comparison_type:
            rows = [row for row in rows if row.get("comparison_type") == comparison_type]
        rows.sort(key=lambda row: row["id"], reverse=True)
        return rows[:limit]

    def get_phrase_observations(self, speaker_name, limit=25, min_rarity=None):
        rows = []
        for document_id, fingerprint in self.fingerprints.items():
            document = self.documents.get(document_id)
            if not document or document.get("speaker_name") != speaker_name:
                continue
            for signal in fingerprint.get("phrase_signals", []):
                row = {
                    "phrase_text": signal["phrase_text"],
                    "normalized_phrase": signal["normalized_phrase"],
                    "semantic_key": signal["semantic_key"],
                    "rarity_score": signal["rarity_score"],
                    "current_count": signal["current_count"],
                    "historical_count": signal["historical_count"],
                    "documents": {
                        "speaker_name": document["speaker_name"],
                        "speech_date": document["speech_date"],
                        "title": document["title"],
                    },
                }
                if min_rarity is None or row["rarity_score"] >= min_rarity:
                    rows.append(row)
        rows.sort(key=lambda row: row["rarity_score"], reverse=True)
        return rows[:limit]


class PersistenceFlowTests(unittest.TestCase):
    def test_pipeline_persists_and_compares_against_history(self):
        db = FakeDatabase()
        pipeline = AnalysisPipeline(extractor=HeuristicFingerprintExtractor(), database=db)

        first = pipeline.analyze_and_store_markdown(
            "Inflation has moderated and labor market conditions have improved.",
            metadata={
                "speaker_name": "Jerome H. Powell",
                "speech_date": "2026-01-10",
                "document_type": "speech",
            },
        )
        self.assertIsNotNone(first.persisted)
        self.assertFalse(first.comparisons)

        second = pipeline.analyze_and_store_markdown(
            "Inflation remains elevated, labor market conditions are tight, and policy may need to stay restrictive.",
            metadata={
                "speaker_name": "Jerome H. Powell",
                "speech_date": "2026-02-10",
                "document_type": "speech",
            },
        )

        self.assertIsNotNone(second.persisted)
        self.assertIn("t_minus_1", second.comparisons)
        self.assertIn("window_75d", second.comparisons)
        self.assertIn("window_24m", second.comparisons)
        self.assertGreaterEqual(len(db.comparisons), 3)


if __name__ == "__main__":
    unittest.main()
