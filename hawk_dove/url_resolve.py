"""Resolve a published speech URL for a calendar speaker event."""

from __future__ import annotations

import re
from datetime import date
from typing import Optional, Sequence
from urllib.parse import urlparse

from hawk_dove.calendar import SpeakerEvent, source_family_for_event
from hawk_dove.discovery import DiscoveredDocument, discover_source_family

_NAME_SPLIT_RE = re.compile(r"[^a-z0-9]+")

# Hosts that are almost never published speech/transcript text.
_REJECT_HOST_SUFFIXES = (
    "zoom.us",
    "zoom.com",
    "webex.com",
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "teams.microsoft.com",
    "gotomeeting.com",
    "eventbrite.com",
)

# Path fragments that indicate livestream/registration shells, not remarks text.
_REJECT_PATH_FRAGMENTS = (
    "/live-broadcast",
    "/live/",
    "/webcast",
    "/register",
    "/registration",
    "/j.php",  # WebEx join links
    "/meeting/register",
)

# Published Fed remarks / press-conference transcript style paths.
_FED_SPEECH_PATH_RE = re.compile(
    r"^/newsevents/(speech|speeches|pressconferences|testimony)/",
    re.IGNORECASE,
)
_NYFED_SPEECH_PATH_RE = re.compile(
    r"^/newsevents/(speech|speeches)/",
    re.IGNORECASE,
)


def _tokens(value: str) -> set[str]:
    return {part for part in _NAME_SPLIT_RE.split(value.lower()) if len(part) > 2}


def _host(netloc: str) -> str:
    return netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")


def _host_endswith(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def is_rejected_event_url(url: str) -> bool:
    """True for livestream/registration/media shells we should never score."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return True
    host = _host(parsed.netloc)
    if any(_host_endswith(host, suffix) for suffix in _REJECT_HOST_SUFFIXES):
        return True
    path = (parsed.path or "").lower()
    if any(fragment in path for fragment in _REJECT_PATH_FRAGMENTS):
        return True
    # Bare congressional landing pages (no substantive path).
    if _host_endswith(host, "house.gov") or _host_endswith(host, "senate.gov"):
        cleaned = path.rstrip("/")
        if cleaned == "" or cleaned.count("/") < 1:
            return True
        # Single-segment roots like "/about" are still not testimony text.
        if cleaned.count("/") == 1 and len(cleaned) < 20:
            return True
    return False


def is_published_speech_url(url: str) -> bool:
    """True when URL looks like a published speech/transcript page worth scoring."""
    if not url or is_rejected_event_url(url):
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = _host(parsed.netloc)
    path = parsed.path or ""

    if _host_endswith(host, "federalreserve.gov"):
        return bool(_FED_SPEECH_PATH_RE.match(path))
    if _host_endswith(host, "newyorkfed.org"):
        return bool(_NYFED_SPEECH_PATH_RE.match(path))
    # Deeper congress paths (uploaded files / hearing pages), not bare sites.
    if _host_endswith(host, "house.gov") or _host_endswith(host, "senate.gov"):
        cleaned = path.rstrip("/")
        return cleaned.count("/") >= 2 and not is_rejected_event_url(url)
    return False


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


def _best_discovery_match(
    event: SpeakerEvent,
    candidates: Sequence[DiscoveredDocument],
    *,
    slack_days: int = 2,
) -> Optional[str]:
    target_date = event.scheduled_date
    matches = [
        item
        for item in candidates
        if is_published_speech_url(item.url)
        and _speaker_match(event, item)
        and _date_close(item, target_date, slack_days=slack_days)
    ]
    if not matches:
        # Loosen date if speaker matches strongly.
        matches = [
            item
            for item in candidates
            if is_published_speech_url(item.url) and _speaker_match(event, item)
        ]
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


def resolve_event_url(
    event: SpeakerEvent,
    *,
    discovered: Optional[Sequence[DiscoveredDocument]] = None,
    session=None,
    slack_days: int = 2,
) -> Optional[str]:
    """Return a published speech URL, or None to retry later.

    Preference order:
    1. Calendar ``event.url`` when it is a published speech/transcript URL
    2. Board / NY Fed discovery match by speaker + date
    3. None (``no_url_resolved``) — never fall back to Zoom/WebEx/YouTube/etc.
    """
    calendar_url = None
    if event.url:
        parsed = urlparse(event.url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            calendar_url = event.url.rstrip("/")

    if calendar_url and is_published_speech_url(calendar_url):
        return calendar_url

    candidates: list[DiscoveredDocument] = list(discovered or [])
    if not candidates:
        for family in source_family_for_event(event):
            candidates.extend(discover_source_family(family, session=session))

    discovered_url = _best_discovery_match(event, candidates, slack_days=slack_days)
    if discovered_url:
        return discovered_url

    # Explicitly do not score rejected calendar URLs; wait for a published text page.
    return None
