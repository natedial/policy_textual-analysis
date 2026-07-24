"""Listing-page discovery for Board and New York Fed speech indexes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional, Sequence
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


@dataclass
class DiscoveredDocument:
    url: str
    source_family: str
    title: Optional[str] = None
    speaker_hint: Optional[str] = None
    date_hint: Optional[date] = None


SOURCE_FAMILIES = {
    "board": {
        "name": "Board of Governors",
        "index_urls": [
            "https://www.federalreserve.gov/newsevents/speeches.htm",
            "https://www.federalreserve.gov/newsevents/speech/",
        ],
        "host_suffix": "federalreserve.gov",
        "path_prefixes": ("/newsevents/speech/",),
    },
    "nyfed": {
        "name": "New York Fed",
        "index_urls": [
            "https://www.newyorkfed.org/newsevents/speeches",
            "https://www.newyorkfed.org/newsevents/speeches/",
        ],
        "host_suffix": "newyorkfed.org",
        "path_prefixes": ("/newsevents/speeches/", "/newsevents/speech/"),
    },
}


DATE_IN_URL_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _parse_date_hint(url: str, text: str = "") -> Optional[date]:
    match = DATE_IN_URL_RE.search(url)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    text_match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if text_match:
        try:
            return date(int(text_match.group(1)), int(text_match.group(2)), int(text_match.group(3)))
        except ValueError:
            return None
    return None


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    cleaned = parsed._replace(fragment="", query="")
    return cleaned.geturl().rstrip("/")


def discover_from_html(
    html: str,
    source_family: str,
    base_url: str,
) -> List[DiscoveredDocument]:
    config = SOURCE_FAMILIES[source_family]
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, DiscoveredDocument] = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        absolute = _normalize_url(urljoin(base_url, href))
        parsed = urlparse(absolute)
        if not parsed.netloc.endswith(config["host_suffix"]):
            continue
        if not any(parsed.path.startswith(prefix) for prefix in config["path_prefixes"]):
            continue
        # Skip bare index pages.
        if parsed.path.rstrip("/").endswith(("speech", "speeches", "newsevents")):
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split()) or None
        found[absolute] = DiscoveredDocument(
            url=absolute,
            source_family=source_family,
            title=title,
            date_hint=_parse_date_hint(absolute, title or ""),
        )
    return list(found.values())


def discover_source_family(
    source_family: str,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> List[DiscoveredDocument]:
    if source_family not in SOURCE_FAMILIES:
        raise ValueError(f"Unsupported source family: {source_family}")
    config = SOURCE_FAMILIES[source_family]
    http = session or requests.Session()
    discovered: dict[str, DiscoveredDocument] = {}
    for index_url in config["index_urls"]:
        try:
            response = http.get(index_url, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException:
            continue
        for item in discover_from_html(response.text, source_family=source_family, base_url=index_url):
            discovered[item.url] = item
    return sorted(discovered.values(), key=lambda item: item.date_hint or date.min, reverse=True)


def discover_new_urls(
    source_families: Sequence[str] = ("board", "nyfed"),
    known_urls: Optional[Iterable[str]] = None,
    session: Optional[requests.Session] = None,
) -> List[DiscoveredDocument]:
    known = {_normalize_url(url) for url in (known_urls or [])}
    results: List[DiscoveredDocument] = []
    for family in source_families:
        for item in discover_source_family(family, session=session):
            if item.url not in known:
                results.append(item)
    return results
