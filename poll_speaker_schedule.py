#!/usr/bin/env python3
"""Poll calendar speaker_events and score due Fed speeches into the corpus DB."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fed_tracker.contract import cli_envelope
from fed_tracker.normalization import normalize_url
from hawk_dove.calendar import (
    DEFAULT_EVENT_TYPES,
    DEFAULT_LOOKAHEAD,
    DEFAULT_LOOKBACK,
    CalendarClient,
    SpeakerEvent,
    filter_due_events,
)
from hawk_dove.officials import OfficialsDirectory
from hawk_dove.pipeline import HawkDovePipeline
from hawk_dove.registry import get_scorer
from hawk_dove.snapshots import materialize_snapshots
from hawk_dove.url_resolve import resolve_event_url


def _parse_hours(value: float) -> timedelta:
    return timedelta(hours=value)


def process_event(
    event: SpeakerEvent,
    *,
    pipeline: HawkDovePipeline,
    corpus_db,
    dry_run: bool = False,
    materialize: bool = True,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "external_id": event.external_id,
        "calendar_event_id": event.id,
        "speaker_name": event.speaker_name,
        "title": event.title,
        "scheduled_start": event.scheduled_start.isoformat(),
        "status": "pending",
    }

    if corpus_db is not None:
        existing = corpus_db.get_calendar_ingest_run(event.external_id)
        if existing and existing.get("status") == "scored":
            result["status"] = "skipped_already_scored"
            result["document_key"] = existing.get("document_key")
            result["score_key"] = existing.get("score_key")
            return result

    try:
        resolved_url = resolve_event_url(event)
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"url_resolve_error: {exc}"
        if corpus_db is not None and not dry_run:
            corpus_db.upsert_calendar_ingest_run(
                {
                    "external_id": event.external_id,
                    "calendar_event_id": event.id,
                    "speaker_name": event.speaker_name,
                    "title": event.title,
                    "scheduled_start": event.scheduled_start.isoformat(),
                    "event_type": event.event_type,
                    "source": event.source,
                    "status": "failed",
                    "error": result["error"],
                }
            )
        return result

    if not resolved_url:
        # Remarks often publish after the event; keep retryable (not a hard fail).
        result["status"] = "pending_url"
        result["error"] = "no_url_resolved"
        if event.url:
            result["rejected_calendar_url"] = event.url
        if corpus_db is not None and not dry_run:
            corpus_db.upsert_calendar_ingest_run(
                {
                    "external_id": event.external_id,
                    "calendar_event_id": event.id,
                    "speaker_name": event.speaker_name,
                    "title": event.title,
                    "scheduled_start": event.scheduled_start.isoformat(),
                    "event_type": event.event_type,
                    "source": event.source,
                    "resolved_url": event.url,
                    "status": "pending_url",
                    "error": result["error"],
                }
            )
        return result

    result["resolved_url"] = resolved_url

    if corpus_db is not None and corpus_db.source_document_exists(resolved_url):
        result["status"] = "skipped_url_exists"
        if not dry_run:
            corpus_db.upsert_calendar_ingest_run(
                {
                    "external_id": event.external_id,
                    "calendar_event_id": event.id,
                    "speaker_name": event.speaker_name,
                    "title": event.title,
                    "scheduled_start": event.scheduled_start.isoformat(),
                    "event_type": event.event_type,
                    "source": event.source,
                    "resolved_url": resolved_url,
                    "status": "scored",
                    "error": None,
                    "scored_at": datetime.now(timezone.utc).isoformat(),
                    "model_version": pipeline.scorer.model_version,
                }
            )
        return result

    if dry_run:
        result["status"] = "dry_run_would_score"
        return result

    try:
        document = normalize_url(resolved_url)
        if event.speaker_name:
            document.speaker_name = event.speaker_name
        if document.speech_date is None:
            document.speech_date = event.scheduled_date
        if event.title and not document.title:
            document.title = event.title
        if event.source and not document.source:
            document.source = event.source
        document.source_metadata = {
            **(document.source_metadata or {}),
            "calendar_external_id": event.external_id,
            "calendar_event_id": event.id,
            "calendar_event_type": event.event_type,
        }

        scored = pipeline.score_document(document, persist=corpus_db is not None)
        obs = scored.observation

        if materialize and corpus_db is not None:
            materialize_snapshots(
                [obs],
                as_of_date=as_of or date.today(),
                database=corpus_db,
                model_version=obs.model_version,
                officials=pipeline.officials,
            )

        result["status"] = "scored"
        result["document_key"] = obs.document_key
        result["score_key"] = obs.score_key
        result["overall_score"] = (
            None if obs.score.insufficient_policy_content else obs.score.overall_score
        )
        result["model_version"] = obs.model_version
        if corpus_db is not None:
            corpus_db.upsert_calendar_ingest_run(
                {
                    "external_id": event.external_id,
                    "calendar_event_id": event.id,
                    "speaker_name": event.speaker_name,
                    "title": event.title,
                    "scheduled_start": event.scheduled_start.isoformat(),
                    "event_type": event.event_type,
                    "source": event.source,
                    "resolved_url": resolved_url,
                    "status": "scored",
                    "error": None,
                    "document_key": obs.document_key,
                    "score_key": obs.score_key,
                    "model_version": obs.model_version,
                    "scored_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        if corpus_db is not None:
            corpus_db.upsert_calendar_ingest_run(
                {
                    "external_id": event.external_id,
                    "calendar_event_id": event.id,
                    "speaker_name": event.speaker_name,
                    "title": event.title,
                    "scheduled_start": event.scheduled_start.isoformat(),
                    "event_type": event.event_type,
                    "source": event.source,
                    "resolved_url": resolved_url,
                    "status": "failed",
                    "error": result["error"],
                }
            )
    return result


def run_poll(
    *,
    method: str = "heuristic",
    lookback_hours: float = 6.0,
    lookahead_hours: float = 2.0,
    event_types: Optional[List[str]] = None,
    dry_run: bool = False,
    persist: bool = True,
    materialize: bool = True,
    now: Optional[datetime] = None,
    calendar_client: Optional[CalendarClient] = None,
    events: Optional[List[SpeakerEvent]] = None,
    corpus_db=None,
) -> Dict[str, Any]:
    officials = OfficialsDirectory()
    scorer = get_scorer(method)
    if persist and corpus_db is None and os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
        from db import Database

        corpus_db = Database()
    pipeline = HawkDovePipeline(
        scorer=scorer,
        officials=officials,
        database=corpus_db if persist else None,
    )

    lookback = _parse_hours(lookback_hours)
    lookahead = _parse_hours(lookahead_hours)
    types = event_types or list(DEFAULT_EVENT_TYPES)

    if events is None:
        client = calendar_client or CalendarClient()
        due_events = client.list_due_events(
            now=now,
            lookback=lookback,
            lookahead=lookahead,
            event_types=types,
        )
    else:
        due_events = filter_due_events(
            events,
            now=now,
            lookback=lookback,
            lookahead=lookahead,
            event_types=types,
        )

    # Skip already scored external_ids in one round-trip when possible.
    if corpus_db is not None and due_events:
        scored_ids = corpus_db.list_scored_calendar_external_ids(
            [event.external_id for event in due_events]
        )
        due_events = [event for event in due_events if event.external_id not in scored_ids]

    results = [
        process_event(
            event,
            pipeline=pipeline,
            corpus_db=corpus_db if persist else None,
            dry_run=dry_run,
            materialize=materialize and persist and not dry_run,
        )
        for event in due_events
    ]

    summary = {
        "due_count": len(results),
        "scored": sum(1 for row in results if row["status"] == "scored"),
        "failed": sum(1 for row in results if row["status"] == "failed"),
        "pending_url": sum(1 for row in results if row["status"] == "pending_url"),
        "skipped": sum(1 for row in results if str(row["status"]).startswith("skipped")),
        "dry_run": dry_run,
        "method": method,
        "lookback_hours": lookback_hours,
        "lookahead_hours": lookahead_hours,
        "event_types": types,
        "results": results,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Poll calendar speaker_events and score due Fed speeches (corpus persist)."
    )
    parser.add_argument("--method", default="heuristic", help="heuristic|roberta")
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK.total_seconds() / 3600)
    parser.add_argument("--lookahead-hours", type=float, default=DEFAULT_LOOKAHEAD.total_seconds() / 3600)
    parser.add_argument(
        "--event-types",
        default=",".join(DEFAULT_EVENT_TYPES),
        help="Comma-separated event_type values to include",
    )
    parser.add_argument("--dry-run", action="store_true", help="Resolve URLs but do not score/persist")
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Score without writing to corpus Supabase",
    )
    parser.add_argument(
        "--no-materialize",
        action="store_true",
        help="Skip EWMA snapshot materialization after scoring",
    )
    args = parser.parse_args()

    payload = run_poll(
        method=args.method,
        lookback_hours=args.lookback_hours,
        lookahead_hours=args.lookahead_hours,
        event_types=[part.strip() for part in args.event_types.split(",") if part.strip()],
        dry_run=args.dry_run,
        persist=not args.no_persist,
        materialize=not args.no_materialize,
    )
    print(json.dumps(cli_envelope(command="poll_speaker_schedule", data=payload), indent=2))


if __name__ == "__main__":
    main()
