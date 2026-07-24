"""Materialize official/committee hawk–dove time-series snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, List, Optional, Sequence

from hawk_dove.aggregation import (
    DEFAULT_HALF_LIFE_DAYS,
    DEFAULT_WINDOW_DAYS,
    aggregate_committee,
    ranked_officials,
)
from hawk_dove.models import CommitteeAggregate, HawkDoveObservation, OfficialAggregate
from hawk_dove.officials import OfficialsDirectory


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "unknown"


def official_snapshot_key(aggregate: OfficialAggregate) -> str:
    return "_".join(
        [
            "official",
            _slug(aggregate.speaker_name),
            aggregate.as_of_date.isoformat(),
            _slug(aggregate.method),
            f"w{aggregate.window_days}",
            _slug(aggregate.model_version or "none"),
            _slug(aggregate.prompt_version or "none"),
            _slug(aggregate.calibration_version or "none"),
        ]
    )


def committee_snapshot_key(aggregate: CommitteeAggregate) -> str:
    return "_".join(
        [
            "committee",
            _slug(aggregate.cohort),
            aggregate.as_of_date.isoformat(),
            _slug(aggregate.method),
            f"w{aggregate.window_days}",
            _slug(aggregate.model_version or "none"),
            _slug(aggregate.prompt_version or "none"),
            _slug(aggregate.calibration_version or "none"),
        ]
    )


def _version_meta(observations: Sequence[HawkDoveObservation]) -> tuple[Optional[str], Optional[str], str]:
    if not observations:
        return None, None, "none"
    return (
        observations[0].prompt_version,
        observations[0].model_version,
        observations[0].calibration_version or "none",
    )


def annotate_versions(
    aggregates: Sequence[OfficialAggregate] | Sequence[CommitteeAggregate],
    observations: Sequence[HawkDoveObservation],
) -> None:
    prompt_version, model_version, calibration_version = _version_meta(observations)
    for row in aggregates:
        row.prompt_version = prompt_version
        row.model_version = model_version
        row.calibration_version = calibration_version


@dataclass
class SnapshotBatch:
    as_of_date: date
    official: List[OfficialAggregate] = field(default_factory=list)
    committee_all: Optional[CommitteeAggregate] = None
    committee_voters: Optional[CommitteeAggregate] = None
    persisted_official_ids: List[int] = field(default_factory=list)
    persisted_committee_ids: List[int] = field(default_factory=list)


def build_snapshot_batch(
    observations: Sequence[HawkDoveObservation],
    as_of_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    aggregation_method: str = "ewma",
    officials: Optional[OfficialsDirectory] = None,
    model_version: Optional[str] = None,
) -> SnapshotBatch:
    officials = officials or OfficialsDirectory()
    filtered = list(observations)
    if model_version:
        filtered = [obs for obs in filtered if obs.model_version == model_version]
    # Keep one methodology branch only.
    if filtered:
        model_version = model_version or filtered[0].model_version
        filtered = [obs for obs in filtered if obs.model_version == model_version]
        prompt_version = filtered[0].prompt_version
        calibration_version = filtered[0].calibration_version
        filtered = [
            obs
            for obs in filtered
            if obs.prompt_version == prompt_version and obs.calibration_version == calibration_version
        ]

    official_rows = ranked_officials(
        filtered,
        as_of_date=as_of_date,
        window_days=window_days,
        half_life_days=half_life_days,
        method=aggregation_method,
        officials=officials,
    )
    annotate_versions(official_rows, filtered)

    committee_all = aggregate_committee(
        filtered,
        as_of_date=as_of_date,
        cohort="all_participants",
        window_days=window_days,
        half_life_days=half_life_days,
        method=aggregation_method,
        officials=officials,
    )
    committee_voters = aggregate_committee(
        filtered,
        as_of_date=as_of_date,
        cohort="voters",
        window_days=window_days,
        half_life_days=half_life_days,
        method=aggregation_method,
        officials=officials,
    )
    annotate_versions([committee_all, committee_voters], filtered)
    annotate_versions(committee_all.official_scores, filtered)
    annotate_versions(committee_voters.official_scores, filtered)

    return SnapshotBatch(
        as_of_date=as_of_date,
        official=official_rows,
        committee_all=committee_all,
        committee_voters=committee_voters,
    )


def materialize_snapshots(
    observations: Sequence[HawkDoveObservation],
    as_of_date: date,
    database,
    window_days: int = DEFAULT_WINDOW_DAYS,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    aggregation_method: str = "ewma",
    officials: Optional[OfficialsDirectory] = None,
    model_version: Optional[str] = None,
) -> SnapshotBatch:
    batch = build_snapshot_batch(
        observations,
        as_of_date=as_of_date,
        window_days=window_days,
        half_life_days=half_life_days,
        aggregation_method=aggregation_method,
        officials=officials,
        model_version=model_version,
    )
    for row in batch.official:
        snapshot_id = database.insert_official_score_snapshot(row, snapshot_key=official_snapshot_key(row))
        batch.persisted_official_ids.append(snapshot_id)
    if batch.committee_all is not None:
        batch.persisted_committee_ids.append(
            database.insert_committee_score_snapshot(
                batch.committee_all,
                snapshot_key=committee_snapshot_key(batch.committee_all),
            )
        )
    if batch.committee_voters is not None:
        batch.persisted_committee_ids.append(
            database.insert_committee_score_snapshot(
                batch.committee_voters,
                snapshot_key=committee_snapshot_key(batch.committee_voters),
            )
        )
    return batch


def observations_from_score_rows(rows: Iterable[dict]) -> List[HawkDoveObservation]:
    """Rebuild lightweight observations from hawk_dove_scores DB rows for aggregation."""
    from hawk_dove.models import HawkDoveScoreResult

    observations: List[HawkDoveObservation] = []
    for row in rows:
        insufficient = bool(row.get("insufficient_policy_content"))
        overall = row.get("overall_score")
        score = HawkDoveScoreResult(
            overall_score=float(overall if overall is not None else 5.0),
            inflation_score=float(row.get("inflation_score") if row.get("inflation_score") is not None else 5.0),
            labor_score=float(row.get("labor_score") if row.get("labor_score") is not None else 5.0),
            growth_score=float(row.get("growth_score") if row.get("growth_score") is not None else 5.0),
            policy_action_score=float(
                row.get("policy_action_score") if row.get("policy_action_score") is not None else 5.0
            ),
            confidence=float(row.get("confidence") or 0.0),
            rationale=row.get("rationale") or "",
            evidence=[],
            insufficient_policy_content=insufficient,
        )
        speech_date = row.get("speech_date")
        observations.append(
            HawkDoveObservation(
                score_key=row.get("score_key") or f"db-{row.get('id')}",
                document_key=str(row.get("document_id") or row.get("score_key") or row.get("id")),
                document_id=row.get("document_id"),
                speaker_name=row.get("speaker_name"),
                speech_date=date.fromisoformat(speech_date) if speech_date else None,
                document_type=row.get("document_type"),
                source_url=row.get("source_url"),
                source_hash=row.get("source_hash") or "unknown",
                score=score,
                prompt_version=row.get("prompt_version") or "unknown",
                model_version=row.get("model_version") or "unknown",
                calibration_version=row.get("calibration_version") or "none",
                was_voter_as_of_date=row.get("was_voter_as_of_date"),
                was_fomc_participant_as_of_date=row.get("was_fomc_participant_as_of_date"),
            )
        )
    return observations
