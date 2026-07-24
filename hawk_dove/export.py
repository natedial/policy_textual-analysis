"""CSV/JSON export helpers for hawk–dove observations and aggregates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Sequence

from hawk_dove.models import CommitteeAggregate, HawkDoveObservation, OfficialAggregate


def observations_to_rows(observations: Sequence[HawkDoveObservation]) -> list[dict]:
    return [obs.to_export_row() for obs in observations]


def export_observations_json(observations: Sequence[HawkDoveObservation], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [obs.model_dump(mode="json") for obs in observations]
    target.write_text(json.dumps(payload, indent=2))
    return target


def export_observations_csv(observations: Sequence[HawkDoveObservation], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = observations_to_rows(observations)
    fieldnames = list(rows[0].keys()) if rows else [
        "score_key",
        "document_key",
        "speaker_name",
        "speech_date",
        "overall_score",
        "inflation_score",
        "labor_score",
        "growth_score",
        "policy_action_score",
        "confidence",
        "insufficient_policy_content",
        "prompt_version",
        "model_version",
    ]
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            if isinstance(serialized.get("evidence_json"), list):
                serialized["evidence_json"] = json.dumps(serialized["evidence_json"])
            writer.writerow(serialized)
    return target


def export_official_aggregates_csv(rows: Sequence[OfficialAggregate], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "speaker_name",
        "as_of_date",
        "method",
        "window_days",
        "half_life_days",
        "overall_score",
        "inflation_score",
        "labor_score",
        "growth_score",
        "policy_action_score",
        "communication_count",
        "was_voter",
        "was_fomc_participant",
        "coverage_notes",
    ]
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "speaker_name": row.speaker_name,
                    "as_of_date": row.as_of_date.isoformat(),
                    "method": row.method,
                    "window_days": row.window_days,
                    "half_life_days": row.half_life_days,
                    "overall_score": row.overall_score,
                    "inflation_score": row.inflation_score,
                    "labor_score": row.labor_score,
                    "growth_score": row.growth_score,
                    "policy_action_score": row.policy_action_score,
                    "communication_count": row.communication_count,
                    "was_voter": row.was_voter,
                    "was_fomc_participant": row.was_fomc_participant,
                    "coverage_notes": json.dumps(row.coverage_notes),
                }
            )
    return target


def export_committee_json(aggregate: CommitteeAggregate, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(aggregate.model_dump(mode="json"), indent=2))
    return target


def write_bundle(
    observations: Sequence[HawkDoveObservation],
    output_dir: str | Path,
    officials: Sequence[OfficialAggregate] | None = None,
    committee: CommitteeAggregate | None = None,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "observations_json": str(export_observations_json(observations, output / "observations.json")),
        "observations_csv": str(export_observations_csv(observations, output / "observations.csv")),
    }
    if officials is not None:
        paths["officials_csv"] = str(export_official_aggregates_csv(officials, output / "official_ranks.csv"))
    if committee is not None:
        paths["committee_json"] = str(export_committee_json(committee, output / "committee.json"))
    return paths
