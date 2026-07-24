"""Hawk–Dove research scoring layer over the shared Fed corpus."""

from hawk_dove.aggregation import (
    DEFAULT_HALF_LIFE_DAYS,
    DEFAULT_WINDOW_DAYS,
    aggregate_committee,
    aggregate_official,
    ranked_officials,
)
from hawk_dove.discovery import discover_new_urls, discover_source_family
from hawk_dove.export import export_observations_csv, export_observations_json, write_bundle
from hawk_dove.models import CommitteeAggregate, HawkDoveObservation, OfficialAggregate
from hawk_dove.officials import OfficialsDirectory, build_seed_memberships
from hawk_dove.pipeline import HawkDovePipeline, build_pipeline
from hawk_dove.scoring import HeuristicHawkDoveScorer, default_scorer

__all__ = [
    "DEFAULT_HALF_LIFE_DAYS",
    "DEFAULT_WINDOW_DAYS",
    "CommitteeAggregate",
    "HawkDoveObservation",
    "HawkDovePipeline",
    "HeuristicHawkDoveScorer",
    "OfficialAggregate",
    "OfficialsDirectory",
    "aggregate_committee",
    "aggregate_official",
    "build_pipeline",
    "build_seed_memberships",
    "default_scorer",
    "discover_new_urls",
    "discover_source_family",
    "export_observations_csv",
    "export_observations_json",
    "ranked_officials",
    "write_bundle",
]
