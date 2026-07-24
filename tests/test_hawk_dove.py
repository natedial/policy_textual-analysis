import json
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path

from hawk_dove.aggregation import (
    aggregate_committee,
    aggregate_official,
    exponential_weight,
    ranked_officials,
)
from hawk_dove.discovery import discover_from_html
from hawk_dove.export import export_observations_csv, export_observations_json
from hawk_dove.models import HawkDoveObservation, HawkDoveScoreResult
from hawk_dove.officials import OfficialsDirectory, build_seed_memberships
from hawk_dove.pipeline import HawkDovePipeline
from hawk_dove.scoring import HeuristicHawkDoveScorer, has_monetary_policy_content


def _obs(
    speaker: str,
    speech_date: date,
    overall: float,
    insufficient: bool = False,
) -> HawkDoveObservation:
    score = HawkDoveScoreResult(
        overall_score=overall,
        inflation_score=overall,
        labor_score=overall,
        growth_score=overall,
        policy_action_score=overall,
        confidence=0.7,
        rationale="test",
        evidence=[],
        insufficient_policy_content=insufficient,
    )
    return HawkDoveObservation(
        document_key=f"{speaker}-{speech_date.isoformat()}-{overall}",
        speaker_name=speaker,
        speech_date=speech_date,
        document_type="speech",
        source_url=None,
        source_hash=f"hash-{speaker}-{speech_date}-{overall}",
        score=score,
        prompt_version="test",
        model_version="test",
    )


class OfficialsTests(unittest.TestCase):
    def test_seed_memberships_include_board_voters(self):
        records = build_seed_memberships([2025])
        powell = [r for r in records if r.name == "Jerome H. Powell"]
        self.assertTrue(powell)
        self.assertTrue(powell[0].is_voting_member)

    def test_voting_resolved_as_of_date(self):
        directory = OfficialsDirectory()
        # NY Fed always votes
        self.assertTrue(directory.is_voting_member("John C. Williams", date(2025, 6, 1)))
        # Chicago votes in 2025
        self.assertTrue(directory.is_voting_member("Austan D. Goolsbee", date(2025, 3, 1)))
        self.assertFalse(directory.is_voting_member("Austan D. Goolsbee", date(2024, 3, 1)))


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = HawkDovePipeline(scorer=HeuristicHawkDoveScorer())

    def test_policy_content_gate(self):
        self.assertFalse(has_monetary_policy_content("Community outreach awards ceremony."))
        self.assertTrue(has_monetary_policy_content("Inflation and labor market policy rates remain important."))

    def test_validation_set_bucket_separation(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "examples/hawk_dove/validation_set.json").read_text())
        scores = {}
        for item in manifest["items"]:
            text = (root / item["path"]).read_text()
            scored = self.pipeline.score_markdown(text, metadata=item.get("metadata") or {})
            scores[item["id"]] = scored.observation
            if item.get("expect_insufficient_policy_content"):
                self.assertTrue(scored.observation.score.insufficient_policy_content)
            else:
                self.assertFalse(scored.observation.score.insufficient_policy_content)
                low = item["human_overall_min"]
                high = item["human_overall_max"]
                # Heuristic should land in the same broad bucket, allow some slack.
                value = scored.observation.score.overall_score
                if item["expected_bucket"] == "hawkish":
                    self.assertGreater(value, 5.5)
                elif item["expected_bucket"] == "dovish":
                    self.assertLess(value, 4.5)
                elif item["expected_bucket"] == "neutral":
                    self.assertGreaterEqual(value, low - 1.5)
                    self.assertLessEqual(value, high + 1.5)

        self.assertGreater(scores["hawkish_1"].score.overall_score, scores["dovish_1"].score.overall_score)

    def test_extreme_scores_include_evidence(self):
        text = Path("examples/hawk_dove/hawkish_speech.md").read_text()
        scored = self.pipeline.score_markdown(
            text,
            metadata={"speaker_name": "Christopher J. Waller", "speech_date": "2025-06-15"},
        )
        if scored.observation.score.overall_score > 6.5:
            self.assertTrue(scored.observation.score.evidence)


class AggregationTests(unittest.TestCase):
    def test_exponential_weight_half_life(self):
        self.assertAlmostEqual(exponential_weight(30, half_life_days=30), 0.5, places=5)
        self.assertTrue(exponential_weight(0) > exponential_weight(10))

    def test_ewma_and_committee_equal_official_weight(self):
        observations = [
            _obs("Jerome H. Powell", date(2025, 6, 1), 8.0),
            _obs("Jerome H. Powell", date(2025, 5, 1), 6.0),
            _obs("John C. Williams", date(2025, 6, 10), 4.0),
        ]
        as_of = date(2025, 6, 15)
        powell = aggregate_official(observations, "Jerome H. Powell", as_of_date=as_of, method="ewma")
        self.assertIsNotNone(powell.overall_score)
        self.assertGreater(powell.overall_score, 6.0)
        self.assertEqual(powell.communication_count, 2)

        committee = aggregate_committee(
            observations,
            as_of_date=as_of,
            cohort="custom",
            officials=OfficialsDirectory(),
        )
        # Equal weight: (powell_ewma + 4.0) / 2
        ranks = ranked_officials(observations, as_of_date=as_of)
        covered = [row for row in ranks if row.overall_score is not None]
        expected = sum(row.overall_score for row in covered) / len(covered)
        self.assertAlmostEqual(committee.overall_score, round(expected, 3), places=3)
        self.assertIn("officials_with_scores", committee.coverage_notes)

    def test_missing_coverage_warning(self):
        observations = [_obs("Jerome H. Powell", date(2024, 1, 1), 7.0)]
        result = aggregate_official(observations, "Jerome H. Powell", as_of_date=date(2025, 6, 1))
        self.assertIsNone(result.overall_score)
        self.assertEqual(result.coverage_notes.get("warning"), "no_qualifying_communications_in_window")


class DiscoveryTests(unittest.TestCase):
    def test_board_html_discovery(self):
        html = """
        <html><body>
          <a href="/newsevents/speech/powell20250618a.htm">Chair Powell Remarks</a>
          <a href="/newsevents/speeches.htm">Speeches index</a>
          <a href="https://example.com/other">Other</a>
        </body></html>
        """
        found = discover_from_html(
            html,
            source_family="board",
            base_url="https://www.federalreserve.gov/newsevents/speeches.htm",
        )
        self.assertEqual(len(found), 1)
        self.assertIn("powell20250618a", found[0].url)
        self.assertEqual(found[0].date_hint, date(2025, 6, 18))

    def test_nyfed_html_discovery(self):
        html = """
        <html><body>
          <a href="/newsevents/speeches/2025/williams20250610">Williams Speech</a>
        </body></html>
        """
        found = discover_from_html(
            html,
            source_family="nyfed",
            base_url="https://www.newyorkfed.org/newsevents/speeches",
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source_family, "nyfed")


class ExportTests(unittest.TestCase):
    def test_export_json_and_csv(self):
        observations = [_obs("Jerome H. Powell", date(2025, 6, 1), 6.5)]
        with tempfile.TemporaryDirectory() as tmp:
            json_path = export_observations_json(observations, Path(tmp) / "obs.json")
            csv_path = export_observations_csv(observations, Path(tmp) / "obs.csv")
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            payload = json.loads(json_path.read_text())
            self.assertEqual(payload[0]["speaker_name"], "Jerome H. Powell")
            self.assertIn("overall_score", csv_path.read_text())


class PipelineVotingTests(unittest.TestCase):
    def test_observation_includes_voting_flags(self):
        pipeline = HawkDovePipeline(scorer=HeuristicHawkDoveScorer())
        text = Path("examples/hawk_dove/neutral_speech.md").read_text()
        scored = pipeline.score_markdown(
            text,
            metadata={
                "speaker_name": "Jerome H. Powell",
                "speech_date": "2025-06-18",
                "document_type": "speech",
            },
        )
        self.assertTrue(scored.observation.was_voter_as_of_date)
        self.assertTrue(scored.observation.was_fomc_participant_as_of_date)


if __name__ == "__main__":
    unittest.main()
