"""Hawk–Dove research scoring layer over the shared Fed corpus."""

from hawk_dove.aggregation import (
    DEFAULT_HALF_LIFE_DAYS,
    DEFAULT_WINDOW_DAYS,
    aggregate_committee,
    aggregate_official,
    ranked_officials,
)
from hawk_dove.calendar import CalendarClient, SpeakerEvent, filter_due_events
from hawk_dove.discovery import discover_new_urls, discover_source_family
from hawk_dove.export import export_method_comparison, export_observations_csv, export_observations_json, write_bundle
from hawk_dove.models import CommitteeAggregate, HawkDoveObservation, OfficialAggregate
from hawk_dove.officials import OfficialsDirectory, build_seed_memberships
from hawk_dove.pipeline import HawkDovePipeline, build_pipeline
from hawk_dove.query import HawkDoveQueryService
from hawk_dove.registry import get_scorer, list_methods
from hawk_dove.roberta import RobertaHawkDoveScorer
from hawk_dove.scoring import HeuristicHawkDoveScorer, default_scorer
from hawk_dove.snapshots import build_snapshot_batch, materialize_snapshots
from hawk_dove.url_resolve import resolve_event_url

__all__ = [
    "DEFAULT_HALF_LIFE_DAYS",
    "DEFAULT_WINDOW_DAYS",
    "CalendarClient",
    "CommitteeAggregate",
    "HawkDoveObservation",
    "HawkDovePipeline",
    "HawkDoveQueryService",
    "HeuristicHawkDoveScorer",
    "OfficialAggregate",
    "OfficialsDirectory",
    "RobertaHawkDoveScorer",
    "SpeakerEvent",
    "aggregate_committee",
    "aggregate_official",
    "build_pipeline",
    "build_seed_memberships",
    "build_snapshot_batch",
    "default_scorer",
    "discover_new_urls",
    "discover_source_family",
    "export_method_comparison",
    "export_observations_csv",
    "export_observations_json",
    "filter_due_events",
    "get_scorer",
    "list_methods",
    "materialize_snapshots",
    "ranked_officials",
    "resolve_event_url",
    "write_bundle",
]
