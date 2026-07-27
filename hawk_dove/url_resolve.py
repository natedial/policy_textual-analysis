"""Resolve a published speech URL for a calendar speaker event."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional, Sequence
from urllib.parse import urlparse

from hawk_dove.calendar import SpeakerEvent, source_family_for_event
from hawk_dove.discovery import DiscoveredDocument, discover_source_family

_NAME_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return {part for part in _NAME_SPLIT_RE.split(value.lower()) if len(part) > 2}


def _speaker_match(event: SpeakerEvent, item: DiscoveredDocument) -> bool:
    if not event.speaker_name:
        return True
    speaker_tokens = _tokens(event.speaker_name)
    haystacks = " ".join(
        filter(None, [item.title or "", item.url, item.speaker_hint or ""])
    ).lower()
    if not speaker_tokens:
        return True
    # Require last-name style token hit when available.
    last = event.speaker_name.split()[-1].lower().strip(".")
    if last and last in haystacks:
        return True
    return any(token in haystacks for token in speaker_tokens)


def _date_close(item: DiscoveredDocument, target: date, slack_days: int = 2) -> bool:
    if item.date_hint is None:
        return True
    return abs((item.date_hint - target).days) <= slack_days


def resolve_event_url(
    event: SpeakerEvent,
    *,
    discovered: Optional[Sequence[DiscoveredDocument]] = None,
    session=None,
    slack_days: int = 2,
) -> Optional[str]:
    """Return a speech URL: event.url if set, else best discovery match."""
    if event.url:
        parsed = urlparse(event.url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return event.url.rstrip("/")

    candidates: list[DiscoveredDocument] = list(discovered or [])
    if not candidates:
        for family in source_family_for_event(event):
            candidates.extend(discover_source_family(family, session=session))

    target_date = event.scheduled_date
    matches = [
        item
        for item in candidates
        if _speaker_match(event, item) and _date_close(item, target_date, slack_days=slack_days)
    ]
    if not matches:
        # Loosen date if speaker matches strongly.
        matches = [item for item in candidates if _speaker_match(event, item)]
        matches = [
            item
            for item in matches
            if item.date_hint is None
            or abs((item.date_hint - target_date).days) <= max(slack_days, 5)
        ]
    if not matches:
        return None

    def sort_key(item: DiscoveredDocument):
        date_delta = 0 if item.date_hint is None else abs((item.date_hint - target_date).days)
        return (date_delta, item.url)

    matches.sort(key=sort_key)
    return matches[0].url
