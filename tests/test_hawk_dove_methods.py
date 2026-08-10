import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import List

from hawk_dove.export import export_method_comparison
from hawk_dove.models import HawkDoveObservation, HawkDoveScoreResult
from hawk_dove.pipeline import HawkDovePipeline
from hawk_dove.query import committee_series_from_rows, official_series_from_rows
from hawk_dove.registry import get_scorer, list_methods
from hawk_dove.roberta import (
    ROBERTA_MODEL_ID,
    RobertaHawkDoveScorer,
    SentencePrediction,
    StubSentenceClassifier,
)
from hawk_dove.snapshots import (
    build_snapshot_batch,
    committee_snapshot_key,
    official_snapshot_key,
)


def _obs(speaker: str, speech_date: date, overall: float, model_version: str = "m1") -> HawkDoveObservation:
    score = HawkDoveScoreResult(
        overall_score=overall,
        inflation_score=overall,
        labor_score=overall,
        growth_score=overall,
        policy_action_score=overall,
        confidence=0.7,
        rationale="test",
        evidence=[],
        insufficient_policy_content=False,
    )
    return HawkDoveObservation(
        document_key=f"{speaker}-{speech_date.isoformat()}-{overall}-{model_version}",
        speaker_name=speaker,
        speech_date=speech_date,
        document_type="speech",
        source_url=None,
        source_hash=f"hash-{speaker}-{speech_date}-{overall}-{model_version}",
        score=score,
        prompt_version="test_prompt",
        model_version=model_version,
        calibration_version="none",
    )


class FixedClassifier:
    def __init__(self, label: str = "hawkish"):
        self.label = label

    def classify(self, texts):
        scores = {"hawkish": 0.8, "neutral": 0.15, "dovish": 0.05}
        if self.label == "dovish":
            scores = {"hawkish": 0.05, "neutral": 0.15, "dovish": 0.8}
        elif self.label == "neutral":
            scores = {"hawkish": 0.2, "neutral": 0.6, "dovish": 0.2}
        return [SentencePrediction(label=self.label, scores=scores, confidence=scores[self.label]) for _ in texts]


class RegistryTests(unittest.TestCase):
    def test_list_methods(self):
        methods = list_methods()
        self.assertIn("heuristic", methods)
        self.assertIn("roberta", methods)
        self.assertNotIn("anthropic", methods)

    def test_anthropic_removed(self):
        with self.assertRaises(ValueError):
            get_scorer("anthropic")

    def test_get_heuristic(self):
        scorer = get_scorer("heuristic")
        self.assertEqual(scorer.model_version, "heuristic-hawkdove-v1")


class RobertaScorerTests(unittest.TestCase):
    def test_stub_roberta_scores_hawkish_text(self):
        scorer = RobertaHawkDoveScorer(classifier=StubSentenceClassifier(), use_transformers=False)
        pipeline = HawkDovePipeline(scorer=scorer)
        text = Path("examples/hawk_dove/hawkish_speech.md").read_text()
        scored = pipeline.score_markdown(
            text,
            metadata={"speaker_name": "Christopher J. Waller", "speech_date": "2025-06-15"},
        )
        self.assertFalse(scored.observation.score.insufficient_policy_content)
        self.assertGreater(scored.observation.score.overall_score, 5.0)
        self.assertEqual(scored.observation.model_version, ROBERTA_MODEL_ID)
        self.assertFalse(scored.observation.model_parameters.get("component_scores_native"))
        self.assertTrue(scored.observation.score.evidence)

    def test_fixed_classifier_component_routing(self):
        scorer = RobertaHawkDoveScorer(classifier=FixedClassifier("hawkish"), use_transformers=False)
        text = (
            "Inflation remains elevated and price pressures persist. "
            "The labor market is tight. Growth is strong. Policy should stay restrictive."
        )
        pipeline = HawkDovePipeline(scorer=scorer)
        scored = pipeline.score_markdown(
            text,
            metadata={"speaker_name": "Jerome H. Powell", "speech_date": "2025-06-18"},
        )
        self.assertGreaterEqual(scored.observation.score.inflation_score, 7.0)
        self.assertGreaterEqual(scored.observation.score.policy_action_score, 7.0)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_keys_include_model_version(self):
        observations = [
            _obs("Jerome H. Powell", date(2025, 6, 1), 7.0, model_version="heuristic-hawkdove-v1"),
            _obs("Jerome H. Powell", date(2025, 5, 1), 6.0, model_version="heuristic-hawkdove-v1"),
        ]
        batch = build_snapshot_batch(observations, as_of_date=date(2025, 6, 15))
        self.assertTrue(batch.official)
        key = official_snapshot_key(batch.official[0])
        self.assertIn("heuristic_hawkdove_v1", key)
        self.assertIn("2025-06-15", key)
        self.assertIsNotNone(batch.committee_all)
        ckey = committee_snapshot_key(batch.committee_all)
        self.assertIn("all_participants", ckey)
        self.assertEqual(batch.official[0].model_version, "heuristic-hawkdove-v1")
        self.assertEqual(batch.committee_voters.model_version, "heuristic-hawkdove-v1")

    def test_materialize_filters_by_model_version(self):
        observations = [
            _obs("Jerome H. Powell", date(2025, 6, 1), 8.0, model_version="model-a"),
            _obs("Jerome H. Powell", date(2025, 6, 1), 2.0, model_version="model-b"),
        ]
        batch_a = build_snapshot_batch(observations, as_of_date=date(2025, 6, 15), model_version="model-a")
        batch_b = build_snapshot_batch(observations, as_of_date=date(2025, 6, 15), model_version="model-b")
        self.assertAlmostEqual(batch_a.official[0].overall_score or 0, 8.0)
        self.assertAlmostEqual(batch_b.official[0].overall_score or 0, 2.0)
        self.assertNotEqual(official_snapshot_key(batch_a.official[0]), official_snapshot_key(batch_b.official[0]))


class CompareExportTests(unittest.TestCase):
    def test_method_comparison_csv(self):
        heuristic = [_obs("Jerome H. Powell", date(2025, 6, 1), 7.0, model_version="heuristic-hawkdove-v1")]
        # Force same document_key for side-by-side join
        roberta = [_obs("Jerome H. Powell", date(2025, 6, 1), 6.0, model_version=ROBERTA_MODEL_ID)]
        roberta[0].document_key = heuristic[0].document_key
        with tempfile.TemporaryDirectory() as tmp:
            path = export_method_comparison(
                {"heuristic": heuristic, "roberta": roberta},
                Path(tmp) / "compare.csv",
            )
            text = path.read_text()
            self.assertIn("heuristic_overall_score", text)
            self.assertIn("roberta_overall_score", text)


class QuerySeriesTests(unittest.TestCase):
    def test_committee_series_delta(self):
        rows = [
            {"as_of_date": "2025-05-01", "overall_score": 5.0, "cohort": "voters", "method": "ewma"},
            {"as_of_date": "2025-06-01", "overall_score": 6.2, "cohort": "voters", "method": "ewma"},
        ]
        series = committee_series_from_rows(rows)
        self.assertIsNone(series[0]["delta_vs_prior_snapshot"])
        self.assertAlmostEqual(series[1]["delta_vs_prior_snapshot"], 1.2)

    def test_official_series_sorted(self):
        rows = [
            {"as_of_date": "2025-06-01", "speaker_name": "A", "overall_score": 6.0},
            {"as_of_date": "2025-05-01", "speaker_name": "A", "overall_score": 5.0},
        ]
        series = official_series_from_rows(rows)
        self.assertEqual(series[0]["as_of_date"], "2025-05-01")
        self.assertEqual(series[1]["as_of_date"], "2025-06-01")


class FakeDatabase:
    def __init__(self):
        self.official = []
        self.committee = []

    def insert_official_score_snapshot(self, aggregate, snapshot_key=None):
        self.official.append((snapshot_key, aggregate))
        return len(self.official)

    def insert_committee_score_snapshot(self, aggregate, snapshot_key=None):
        self.committee.append((snapshot_key, aggregate))
        return len(self.committee)


class PersistMaterializeTests(unittest.TestCase):
    def test_materialize_snapshots_writes_versioned_rows(self):
        from hawk_dove.snapshots import materialize_snapshots

        observations = [
            _obs("Jerome H. Powell", date(2025, 6, 1), 7.5, model_version="heuristic-hawkdove-v1"),
            _obs("John C. Williams", date(2025, 6, 10), 4.5, model_version="heuristic-hawkdove-v1"),
        ]
        db = FakeDatabase()
        batch = materialize_snapshots(
            observations,
            as_of_date=date(2025, 6, 15),
            database=db,
            model_version="heuristic-hawkdove-v1",
        )
        self.assertTrue(db.official)
        self.assertEqual(len(db.committee), 2)
        self.assertTrue(all("heuristic_hawkdove_v1" in key for key, _ in db.official))
        self.assertEqual(len(batch.persisted_official_ids), len(db.official))


if __name__ == "__main__":
    unittest.main()
