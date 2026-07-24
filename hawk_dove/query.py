"""Query helpers for stored hawk–dove official/committee time series."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from hawk_dove.aggregation import change_since
from hawk_dove.models import CommitteeAggregate, OfficialAggregate


def official_series_from_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: row.get("as_of_date") or "")
    series: List[Dict[str, Any]] = []
    for row in ordered:
        series.append(
            {
                "speaker_name": row.get("speaker_name"),
                "as_of_date": row.get("as_of_date"),
                "overall_score": row.get("overall_score"),
                "inflation_score": row.get("inflation_score"),
                "labor_score": row.get("labor_score"),
                "growth_score": row.get("growth_score"),
                "policy_action_score": row.get("policy_action_score"),
                "communication_count": row.get("communication_count"),
                "method": row.get("method"),
                "model_version": row.get("model_version"),
                "prompt_version": row.get("prompt_version"),
                "calibration_version": row.get("calibration_version"),
                "coverage_notes": row.get("coverage_notes") or {},
            }
        )
    return series


def committee_series_from_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: row.get("as_of_date") or "")
    series: List[Dict[str, Any]] = []
    previous_score = None
    for row in ordered:
        overall = row.get("overall_score")
        delta = None if previous_score is None or overall is None else round(float(overall) - float(previous_score), 3)
        series.append(
            {
                "as_of_date": row.get("as_of_date"),
                "cohort": row.get("cohort"),
                "overall_score": overall,
                "delta_vs_prior_snapshot": delta,
                "official_count": row.get("official_count"),
                "communication_count": row.get("communication_count"),
                "method": row.get("method"),
                "model_version": row.get("model_version"),
                "prompt_version": row.get("prompt_version"),
                "calibration_version": row.get("calibration_version"),
                "coverage_notes": row.get("coverage_notes") or {},
            }
        )
        if overall is not None:
            previous_score = overall
    return series


class HawkDoveQueryService:
    def __init__(self, database):
        self.database = database

    def official_history(
        self,
        speaker_name: str,
        model_version: Optional[str] = None,
        method: str = "ewma",
        limit: int = 90,
    ) -> List[Dict[str, Any]]:
        rows = self.database.get_official_score_snapshots(
            speaker_name=speaker_name,
            model_version=model_version,
            method=method,
            limit=limit,
        )
        return official_series_from_rows(rows)

    def committee_history(
        self,
        cohort: str = "voters",
        model_version: Optional[str] = None,
        method: str = "ewma",
        limit: int = 90,
    ) -> List[Dict[str, Any]]:
        rows = self.database.get_committee_score_snapshots(
            cohort=cohort,
            model_version=model_version,
            method=method,
            limit=limit,
        )
        return committee_series_from_rows(rows)

    def latest_committee(
        self,
        cohort: str = "voters",
        model_version: Optional[str] = None,
        method: str = "ewma",
    ) -> Optional[Dict[str, Any]]:
        series = self.committee_history(
            cohort=cohort,
            model_version=model_version,
            method=method,
            limit=1,
        )
        return series[-1] if series else None

    def change_since_prior_snapshot(
        self,
        cohort: str = "voters",
        model_version: Optional[str] = None,
        method: str = "ewma",
    ) -> Optional[float]:
        series = self.committee_history(
            cohort=cohort,
            model_version=model_version,
            method=method,
            limit=2,
        )
        if len(series) < 2:
            return None
        current = series[-1].get("overall_score")
        previous = series[-2].get("overall_score")
        if current is None or previous is None:
            return None
        return round(float(current) - float(previous), 3)
