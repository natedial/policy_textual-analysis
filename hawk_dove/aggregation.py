"""Official and committee hawk–dove aggregation."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from hawk_dove.models import CommitteeAggregate, HawkDoveObservation, OfficialAggregate
from hawk_dove.officials import OfficialsDirectory


DEFAULT_WINDOW_DAYS = 90
DEFAULT_HALF_LIFE_DAYS = 30.0


def _parse_date(value: Optional[date | str]) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def exponential_weight(age_days: float, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    if half_life_days <= 0:
        return 1.0
    return math.exp(-math.log(2.0) * age_days / half_life_days)


def _qualifying(observations: Iterable[HawkDoveObservation]) -> List[HawkDoveObservation]:
    return [obs for obs in observations if not obs.score.insufficient_policy_content]


def filter_window(
    observations: Sequence[HawkDoveObservation],
    as_of_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> List[HawkDoveObservation]:
    floor = as_of_date - timedelta(days=window_days)
    selected: List[HawkDoveObservation] = []
    for obs in _qualifying(observations):
        speech_date = obs.speech_date
        if speech_date is None:
            continue
        if floor <= speech_date <= as_of_date:
            selected.append(obs)
    return selected


def aggregate_official(
    observations: Sequence[HawkDoveObservation],
    speaker_name: str,
    as_of_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    method: str = "ewma",
    officials: Optional[OfficialsDirectory] = None,
) -> OfficialAggregate:
    speaker_obs = [obs for obs in observations if (obs.speaker_name or "").lower() == speaker_name.lower()]
    windowed = filter_window(speaker_obs, as_of_date=as_of_date, window_days=window_days)

    coverage = {
        "window_days": window_days,
        "half_life_days": half_life_days,
        "qualifying_communications": len(windowed),
        "missing_speech_dates": sum(1 for obs in speaker_obs if obs.speech_date is None),
    }

    membership = None
    was_voter = None
    was_participant = None
    if officials:
        membership, was_voter, was_participant = officials.resolve(speaker_name, as_of_date)

    if not windowed:
        return OfficialAggregate(
            speaker_name=speaker_name,
            as_of_date=as_of_date,
            method=method,
            window_days=window_days,
            half_life_days=half_life_days,
            overall_score=None,
            communication_count=0,
            coverage_notes={**coverage, "warning": "no_qualifying_communications_in_window"},
            was_voter=was_voter,
            was_fomc_participant=was_participant,
        )

    if method == "latest":
        latest = max(windowed, key=lambda obs: (obs.speech_date or date.min, obs.scored_at))
        score = latest.score
        return OfficialAggregate(
            speaker_name=speaker_name,
            as_of_date=as_of_date,
            method=method,
            window_days=window_days,
            half_life_days=None,
            overall_score=score.overall_score,
            inflation_score=score.inflation_score,
            labor_score=score.labor_score,
            growth_score=score.growth_score,
            policy_action_score=score.policy_action_score,
            communication_count=1,
            coverage_notes=coverage,
            score_keys=[latest.score_key],
            was_voter=was_voter,
            was_fomc_participant=was_participant,
        )

    if method == "mean":
        weights = [1.0 for _ in windowed]
    else:
        weights = [
            exponential_weight((as_of_date - obs.speech_date).days, half_life_days=half_life_days)
            for obs in windowed
        ]

    weight_sum = sum(weights) or 1.0

    def weighted(attr: str) -> float:
        return sum(getattr(obs.score, attr) * weight for obs, weight in zip(windowed, weights)) / weight_sum

    return OfficialAggregate(
        speaker_name=speaker_name,
        as_of_date=as_of_date,
        method=method,
        window_days=window_days,
        half_life_days=half_life_days if method == "ewma" else None,
        overall_score=round(weighted("overall_score"), 3),
        inflation_score=round(weighted("inflation_score"), 3),
        labor_score=round(weighted("labor_score"), 3),
        growth_score=round(weighted("growth_score"), 3),
        policy_action_score=round(weighted("policy_action_score"), 3),
        communication_count=len(windowed),
        coverage_notes=coverage,
        score_keys=[obs.score_key for obs in windowed],
        was_voter=was_voter,
        was_fomc_participant=was_participant,
    )


def ranked_officials(
    observations: Sequence[HawkDoveObservation],
    as_of_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    method: str = "ewma",
    officials: Optional[OfficialsDirectory] = None,
) -> List[OfficialAggregate]:
    names = sorted({obs.speaker_name for obs in observations if obs.speaker_name})
    rows = [
        aggregate_official(
            observations,
            speaker_name=name,
            as_of_date=as_of_date,
            window_days=window_days,
            half_life_days=half_life_days,
            method=method,
            officials=officials,
        )
        for name in names
    ]
    scored = [row for row in rows if row.overall_score is not None]
    missing = [row for row in rows if row.overall_score is None]
    scored.sort(key=lambda row: row.overall_score or 0.0, reverse=True)
    return scored + missing


def aggregate_committee(
    observations: Sequence[HawkDoveObservation],
    as_of_date: date,
    cohort: str = "all_participants",
    window_days: int = DEFAULT_WINDOW_DAYS,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    method: str = "ewma",
    officials: Optional[OfficialsDirectory] = None,
) -> CommitteeAggregate:
    officials = officials or OfficialsDirectory()
    ranked = ranked_officials(
        observations,
        as_of_date=as_of_date,
        window_days=window_days,
        half_life_days=half_life_days,
        method=method,
        officials=officials,
    )

    if cohort == "voters":
        expected = officials.list_participants(as_of_date, voters_only=True)
        expected_names = {r.name.lower() for r in expected}
        cohort_rows = [
            row for row in ranked
            if (row.was_voter is True) or (row.speaker_name or "").lower() in expected_names
        ]
        # Include expected voters with no coverage as missing rows.
        present = {(row.speaker_name or "").lower() for row in cohort_rows}
        for record in expected:
            if record.name.lower() not in present:
                cohort_rows.append(
                    OfficialAggregate(
                        speaker_name=record.name,
                        as_of_date=as_of_date,
                        method=method,
                        window_days=window_days,
                        half_life_days=half_life_days,
                        overall_score=None,
                        communication_count=0,
                        coverage_notes={"warning": "no_qualifying_communications_in_window"},
                        was_voter=True,
                        was_fomc_participant=True,
                    )
                )
    elif cohort == "all_participants":
        expected = officials.list_participants(as_of_date, voters_only=False)
        expected_names = {r.name.lower() for r in expected}
        cohort_rows = [
            row for row in ranked
            if (row.was_fomc_participant is True) or (row.speaker_name or "").lower() in expected_names
        ]
        if not cohort_rows:
            cohort_rows = ranked
    else:
        cohort_rows = ranked

    covered = [row for row in cohort_rows if row.overall_score is not None]
    communication_count = sum(row.communication_count for row in covered)
    overall = None
    if covered:
        # Equalize official-level weights before committee average.
        overall = round(sum(row.overall_score or 0.0 for row in covered) / len(covered), 3)

    coverage_notes = {
        "cohort": cohort,
        "officials_with_scores": len(covered),
        "officials_missing_scores": len(cohort_rows) - len(covered),
        "communication_count": communication_count,
        "equal_weight_per_official": True,
    }
    if not covered:
        coverage_notes["warning"] = "no_qualifying_officials_in_window"

    return CommitteeAggregate(
        as_of_date=as_of_date,
        cohort=cohort,
        method=method,
        window_days=window_days,
        half_life_days=half_life_days,
        overall_score=overall,
        official_count=len(covered),
        communication_count=communication_count,
        coverage_notes=coverage_notes,
        official_scores=cohort_rows,
    )


def change_since(
    current: CommitteeAggregate,
    previous: Optional[CommitteeAggregate],
) -> Optional[float]:
    if previous is None or current.overall_score is None or previous.overall_score is None:
        return None
    return round(current.overall_score - previous.overall_score, 3)


def group_observations_by_speaker(
    observations: Sequence[HawkDoveObservation],
) -> Dict[str, List[HawkDoveObservation]]:
    grouped: Dict[str, List[HawkDoveObservation]] = defaultdict(list)
    for obs in observations:
        if obs.speaker_name:
            grouped[obs.speaker_name].append(obs)
    return grouped
