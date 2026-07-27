"""Read due Fed speaker events from the calendar Supabase project.

Calendar project table: public.speaker_events
Corpus ingest status lives separately in calendar_ingest_runs (this repo's DB).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

DEFAULT_LOOKBACK = timedelta(hours=6)
DEFAULT_LOOKAHEAD = timedelta(hours=2)

# Speech-like event types. Broad on purpose until calendar owners confirm enums.
DEFAULT_EVENT_TYPES = (
    "speech",
    "remarks",
    "testimony",
    "prepared_remarks",
    "press_conference",
    "interview",
    "statement",
)

TERMINAL_STATUSES = frozenset({"cancelled", "canceled", "withdrawn"})


@dataclass
class SpeakerEvent:
    id: int
    external_id: str
    speaker_name: Optional[str]
    title: str
    event_type: str
    scheduled_start: datetime
    scheduled_end: Optional[datetime]
    location: Optional[str]
    description: Optional[str]
    url: Optional[str]
    source: str
    status: str
    calendar_speaker_id: Optional[int] = None
    raw_payload: Optional[Dict[str, Any]] = None

    @property
    def scheduled_date(self):
        return self.scheduled_start.astimezone(timezone.utc).date()


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def speaker_event_from_row(row: Dict[str, Any]) -> SpeakerEvent:
    return SpeakerEvent(
        id=int(row["id"]),
        external_id=str(row["external_id"]),
        speaker_name=row.get("speaker_name"),
        title=row.get("title") or "",
        event_type=str(row.get("event_type") or ""),
        scheduled_start=_parse_dt(row["scheduled_start"]),
        scheduled_end=_parse_dt(row["scheduled_end"]) if row.get("scheduled_end") else None,
        location=row.get("location"),
        description=row.get("description"),
        url=row.get("url") or None,
        source=row.get("source") or "Federal Reserve Board",
        status=str(row.get("status") or "scheduled"),
        calendar_speaker_id=row.get("speaker_id"),
        raw_payload=row.get("raw_payload"),
    )


def is_actionable_status(status: str) -> bool:
    return status.strip().lower() not in TERMINAL_STATUSES


def filter_due_events(
    rows: Sequence[Dict[str, Any]] | Sequence[SpeakerEvent],
    *,
    now: Optional[datetime] = None,
    lookback: timedelta = DEFAULT_LOOKBACK,
    lookahead: timedelta = DEFAULT_LOOKAHEAD,
    event_types: Optional[Iterable[str]] = None,
) -> List[SpeakerEvent]:
    """Filter in-memory rows/events to the due window (also used by unit tests)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    window_start = now - lookback
    window_end = now + lookahead
    allowed_types = {t.lower() for t in (event_types or DEFAULT_EVENT_TYPES)}

    events: List[SpeakerEvent] = []
    for item in rows:
        event = item if isinstance(item, SpeakerEvent) else speaker_event_from_row(item)
        if not is_actionable_status(event.status):
            continue
        if event.event_type.lower() not in allowed_types:
            continue
        if window_start <= event.scheduled_start <= window_end:
            events.append(event)
    events.sort(key=lambda event: event.scheduled_start)
    return events


class CalendarClient:
    """Thin read client for the separate calendar Supabase project."""

    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        table: str = "speaker_events",
    ):
        self.url = supabase_url or os.getenv("CALENDAR_SUPABASE_URL")
        self.key = supabase_key or os.getenv("CALENDAR_SUPABASE_KEY")
        self.table = table
        if not self.url or not self.key:
            raise ValueError("CALENDAR_SUPABASE_URL and CALENDAR_SUPABASE_KEY must be set")
        from supabase import create_client

        self.client = create_client(self.url, self.key)

    def list_due_events(
        self,
        *,
        now: Optional[datetime] = None,
        lookback: timedelta = DEFAULT_LOOKBACK,
        lookahead: timedelta = DEFAULT_LOOKAHEAD,
        event_types: Optional[Sequence[str]] = None,
        limit: int = 200,
    ) -> List[SpeakerEvent]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        window_start = (now - lookback).isoformat()
        window_end = (now + lookahead).isoformat()
        types = list(event_types or DEFAULT_EVENT_TYPES)

        query = (
            self.client.table(self.table)
            .select("*")
            .gte("scheduled_start", window_start)
            .lte("scheduled_start", window_end)
            .in_("event_type", types)
            .order("scheduled_start")
            .limit(limit)
        )
        result = query.execute()
        return filter_due_events(
            result.data or [],
            now=now,
            lookback=lookback,
            lookahead=lookahead,
            event_types=types,
        )


def source_family_for_event(event: SpeakerEvent) -> tuple[str, ...]:
    source = (event.source or "").lower()
    name = (event.speaker_name or "").lower()
    if "new york" in source or "ny fed" in source or "williams" in name:
        return ("board", "nyfed")
    return ("board", "nyfed")
