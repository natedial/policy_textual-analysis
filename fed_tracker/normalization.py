from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from io import BytesIO
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4

import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

from fed_tracker.models import ContentType, DocumentSegment, DocumentType, NormalizedDocument, SegmentType


FED_SOURCES = {
    "federalreserve.gov": "Board of Governors",
    "newyorkfed.org": "New York Fed",
    "kansascityfed.org": "Kansas City Fed",
    "clevelandfed.org": "Cleveland Fed",
    "dallasfed.org": "Dallas Fed",
    "bostonfed.org": "Boston Fed",
    "frbsf.org": "San Francisco Fed",
    "minneapolisfed.org": "Minneapolis Fed",
    "stlouisfed.org": "St. Louis Fed",
    "chicagofed.org": "Chicago Fed",
    "atlantafed.org": "Atlanta Fed",
    "philadelphiafed.org": "Philadelphia Fed",
    "richmondfed.org": "Richmond Fed",
}

FED_CONTENT_SELECTORS = [
    ".col-xs-12.col-sm-8.col-md-8",
    ".eventlist",
    ".col-md-8",
    "main",
    "article",
]

SITE_CONFIGS = {
    "federalreserve.gov": {
        "content_selectors": [
            ".col-xs-12.col-sm-8.col-md-8",
            ".article",
            "main",
        ],
        "title_selectors": ["h3.title", "h1.title", ".pageheader h1"],
        "speaker_selectors": [".speaker", ".speakerName"],
        "date_selectors": [".speakerDate", ".article__time", "time"],
    },
    "newyorkfed.org": {
        "content_selectors": [
            ".ts-article-text",
            ".rich-text",
            ".article-body",
            ".mod-content",
            "main",
        ],
        "title_selectors": [".ts-article-title", "h1", ".hero__title"],
        "speaker_selectors": [".ts-contact-info + .ts-contact-info", ".speaker", ".article__author", ".content-author"],
        "date_selectors": [".ts-contact-info", "time", ".article__date", ".content-date"],
    },
    "kansascityfed.org": {
        "content_selectors": [".wysiwyg", ".article-body", ".main-content", "main"],
        "title_selectors": ["h1", ".page-title", ".article-title"],
        "speaker_selectors": [".speaker", ".author", ".article-meta__author"],
        "date_selectors": ["time", ".article-date", ".date"],
    },
    "clevelandfed.org": {
        "content_selectors": [".article-body", ".rte", ".content-body", "main"],
        "title_selectors": ["h1", ".article-title", ".page-title"],
        "speaker_selectors": [".speaker", ".author", ".article-author"],
        "date_selectors": ["time", ".article-date", ".date"],
    },
    "dallasfed.org": {
        "content_selectors": [".dal-main-content", ".article-body", ".field-name-body", ".rich-text", "main"],
        "title_selectors": [".dal-headline", "h1", ".page-title", ".article__title"],
        "speaker_selectors": [".dal-author", ".speaker", ".field-name-field-author", ".author"],
        "date_selectors": [".dal-content-date", "time", ".date-display-single", ".article-date"],
    },
    "bostonfed.org": {
        "content_selectors": [".rich-text", ".copy", ".article-body", "main"],
        "title_selectors": ["h1", ".hero-title", ".page-title"],
        "speaker_selectors": [".speaker", ".author", ".content-author"],
        "date_selectors": ["time", ".date", ".content-date"],
    },
    "frbsf.org": {
        "content_selectors": [".entry-content", ".wysiwyg", ".article-content", "main"],
        "title_selectors": ["h1", ".entry-title", ".page-title"],
        "speaker_selectors": [".speaker", ".author", ".post-author"],
        "date_selectors": ["time", ".entry-date", ".published"],
    },
    "minneapolisfed.org": {
        "content_selectors": [".article-body", ".story-body", ".wysiwyg", "main"],
        "title_selectors": ["h1", ".article-title", ".page-title"],
        "speaker_selectors": [".speaker", ".author", ".story-author"],
        "date_selectors": ["time", ".article-date", ".story-date"],
    },
    "stlouisfed.org": {
        "content_selectors": [".article-body", ".rich-text", ".body-copy", "main"],
        "title_selectors": ["h1", ".article-title", ".page-title"],
        "speaker_selectors": [".speaker", ".author", ".meta-author"],
        "date_selectors": ["time", ".article-date", ".meta-date"],
    },
    "chicagofed.org": {
        "content_selectors": [".article-body", ".component--rich-text", ".rich-text", "main"],
        "title_selectors": ["h1", ".page-title", ".article-title"],
        "speaker_selectors": [".speaker", ".author", ".article-author"],
        "date_selectors": ["time", ".article-date", ".date"],
    },
    "atlantafed.org": {
        "content_selectors": [".article-body", ".richText", ".rte", "main"],
        "title_selectors": ["h1", ".page-title", ".hero-title"],
        "speaker_selectors": [".speaker", ".author", ".article__author"],
        "date_selectors": ["time", ".date", ".article__date"],
    },
    "philadelphiafed.org": {
        "content_selectors": [".article-body", ".rich-text", ".body-content", "main"],
        "title_selectors": ["h1", ".page-title", ".article-title"],
        "speaker_selectors": [".speaker", ".author", ".article-author"],
        "date_selectors": ["time", ".article-date", ".published-date"],
    },
    "richmondfed.org": {
        "content_selectors": [".article-body", ".wysiwyg", ".content-body", "main"],
        "title_selectors": ["h1", ".page-title", ".article-title"],
        "speaker_selectors": [".speaker", ".author", ".article-author"],
        "date_selectors": ["time", ".article-date", ".date"],
    },
}

BOILERPLATE_PATTERNS = {
    DocumentType.PRESS_RELEASE: [
        re.compile(r"information received since the federal open market committee met", re.IGNORECASE),
        re.compile(r"the committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run", re.IGNORECASE),
        re.compile(r"in support of these goals, the committee decided to", re.IGNORECASE),
        re.compile(r"voting for the monetary policy action were", re.IGNORECASE),
        re.compile(r"the committee will continue reducing its holdings of treasury securities", re.IGNORECASE),
    ],
    DocumentType.STATEMENT: [
        re.compile(r"the committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run", re.IGNORECASE),
        re.compile(r"the committee would be prepared to adjust the stance of monetary policy as appropriate", re.IGNORECASE),
        re.compile(r"in considering the extent of additional policy firming", re.IGNORECASE),
        re.compile(r"in assessing the appropriate stance of monetary policy", re.IGNORECASE),
    ],
    DocumentType.PRESS_CONFERENCE: [
        re.compile(r"thank you\.? i'?m happy to take your questions", re.IGNORECASE),
        re.compile(r"let me say a few words about", re.IGNORECASE),
    ],
}

SOURCE_BOILERPLATE_PATTERNS = {
    "Board of Governors": {
        DocumentType.PRESS_RELEASE: [
            re.compile(r"for media inquiries, call \d{3}-\d{3}-\d{4}", re.IGNORECASE),
        ],
    },
    "New York Fed": {
        DocumentType.PRESS_RELEASE: [
            re.compile(r"contact .*?press office", re.IGNORECASE),
        ],
    },
}

SPEAKER_BOILERPLATE_PATTERNS = {
    "Jerome H. Powell": {
        DocumentType.PRESS_CONFERENCE: [
            re.compile(r"thank you\.? i'?ll be glad to take your questions", re.IGNORECASE),
        ],
    },
}

DATE_PATTERNS = [
    re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
]

Q_PREFIX = re.compile(r"^(q\.|question:)", re.IGNORECASE)
A_PREFIX = re.compile(r"^(a\.|answer:)", re.IGNORECASE)


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _detect_source(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    hostname = urlparse(url).hostname or ""
    for domain, label in FED_SOURCES.items():
        if hostname.endswith(domain):
            return label
    return hostname or None


def _site_config(url: Optional[str]) -> Optional[Dict[str, List[str]]]:
    if not url:
        return None
    hostname = urlparse(url).hostname or ""
    for domain, config in SITE_CONFIGS.items():
        if hostname.endswith(domain):
            return config
    return None


def _detect_document_type(text: str, title: Optional[str], url: Optional[str]) -> DocumentType:
    haystacks = " ".join(part for part in [text[:2000], title or "", url or ""] if part).lower()
    if "press conference" in haystacks:
        return DocumentType.PRESS_CONFERENCE
    if "press release" in haystacks:
        return DocumentType.PRESS_RELEASE
    if "testimony" in haystacks:
        return DocumentType.TESTIMONY
    if "interview" in haystacks:
        return DocumentType.INTERVIEW
    if "question-and-answer" in haystacks or "questions and answers" in haystacks or "q&a" in haystacks:
        return DocumentType.QA_TRANSCRIPT
    if "statement" in haystacks:
        return DocumentType.STATEMENT
    if "remarks" in haystacks:
        return DocumentType.PREPARED_REMARKS
    if "minutes" in haystacks:
        return DocumentType.STATEMENT
    if "speech" in haystacks:
        return DocumentType.SPEECH
    return DocumentType.UNKNOWN


def _is_fed_domain(url: Optional[str]) -> bool:
    if not url:
        return False
    hostname = urlparse(url).hostname or ""
    return any(hostname.endswith(domain) for domain in FED_SOURCES)


def _extract_title(soup: Optional[BeautifulSoup], fallback_url: Optional[str]) -> Optional[str]:
    if soup:
        for selector in ["h3.title", "h1.title", ".article__header h1", ".pageheader h1"]:
            node = soup.select_one(selector)
            if node and node.get_text(strip=True):
                return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if soup.title and soup.title.text.strip():
            return re.sub(r"\s+", " ", soup.title.text).strip()
        meta_title = soup.find("meta", attrs={"property": "og:title"})
        if meta_title and meta_title.get("content"):
            return meta_title["content"].strip()
        h1 = soup.find(["h1", "h2"])
        if h1 and h1.get_text(strip=True):
            return h1.get_text(" ", strip=True)
    if fallback_url:
        return fallback_url.rstrip("/").split("/")[-1]
    return None


def _extract_title_for_site(
    soup: Optional[BeautifulSoup],
    fallback_url: Optional[str],
    selectors: Optional[List[str]] = None,
) -> Optional[str]:
    if soup and selectors:
        for selector in selectors:
            node = soup.select_one(selector)
            if node and node.get_text(strip=True):
                return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
    return _extract_title(soup, fallback_url)


def _extract_date(text: str, soup: Optional[BeautifulSoup], selectors: Optional[List[str]] = None) -> Optional[date]:
    candidates: List[str] = []
    if soup:
        for attr in ["article:published_time", "pubdate", "date", "dc.date"]:
            meta = soup.find("meta", attrs={"property": attr}) or soup.find("meta", attrs={"name": attr})
            if meta and meta.get("content"):
                candidates.append(meta["content"])

        for selector in (selectors or [".article__time", "time", ".pubdate", ".datetime", ".speakerDate"]):
            node = soup.select_one(selector)
            if node and node.get_text(strip=True):
                candidates.append(node.get_text(" ", strip=True))

    candidates.extend(match.group(0) for pattern in DATE_PATTERNS for match in pattern.finditer(text[:5000]))

    for raw in candidates:
        raw = raw.strip()
        try:
            if re.match(r"\d{4}-\d{2}-\d{2}", raw):
                year, month, day = [int(part) for part in raw[:10].split("-")]
                return date(year, month, day)
            return datetime.strptime(raw, "%B %d, %Y").date()
        except Exception:
            continue
    return None


def _extract_speaker(text: str, soup: Optional[BeautifulSoup], selectors: Optional[List[str]] = None) -> Optional[str]:
    if soup:
        for selector in [
            ("meta", {"name": "author"}),
            ("meta", {"property": "article:author"}),
        ]:
            node = soup.find(selector[0], attrs=selector[1])
            if node and node.get("content"):
                return node["content"].strip()

        for selector in (selectors or [".speaker", ".author", ".article__author", ".speakerName"]):
            node = soup.select_one(selector)
            if node and node.get_text(strip=True):
                return node.get_text(" ", strip=True)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:15]:
        if len(line.split()) <= 8 and any(token[0].isupper() for token in line.split() if token):
            lowered = line.lower()
            if "federal reserve" not in lowered and "board of governors" not in lowered:
                return line
    return None


def _clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _html_to_text(content: bytes) -> Tuple[str, BeautifulSoup]:
    soup = BeautifulSoup(content, "html.parser")
    for node in soup(["script", "style", "nav", "footer", "header", "aside"]):
        node.decompose()

    paragraphs = []
    for selector in FED_CONTENT_SELECTORS:
        selector_paragraphs = []
        for container in soup.select(selector):
            selector_paragraphs.extend(
                p.get_text(" ", strip=True)
                for p in container.find_all(["p", "li", "h1", "h2", "h3", "blockquote"])
            )
        if selector_paragraphs:
            paragraphs = selector_paragraphs
            if sum(len(part) for part in paragraphs) >= 500:
                break

    if not paragraphs:
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "li", "h1", "h2", "h3"])]
    text = "\n\n".join(part for part in paragraphs if part)
    if len(text) < 500:
        text = soup.get_text("\n")
    return _clean_text(text), soup


def _html_to_text_for_site(content: bytes, selectors: Optional[List[str]] = None) -> Tuple[str, BeautifulSoup]:
    soup = BeautifulSoup(content, "html.parser")
    for node in soup(["script", "style", "nav", "footer", "header", "aside"]):
        node.decompose()

    paragraphs = []
    for selector in (selectors or FED_CONTENT_SELECTORS):
        selector_paragraphs = []
        for container in soup.select(selector):
            selector_paragraphs.extend(
                p.get_text(" ", strip=True)
                for p in container.find_all(["p", "li", "h1", "h2", "h3", "blockquote"])
            )
        if selector_paragraphs:
            paragraphs = selector_paragraphs
            if sum(len(part) for part in paragraphs) >= 300:
                break

    if not paragraphs:
        return _html_to_text(content)

    text = "\n\n".join(part for part in paragraphs if part)
    return _clean_text(text), soup


def _refine_fed_text(text: str, title: Optional[str]) -> str:
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    filtered: List[str] = []
    seen_title = False

    for block in blocks:
        lowered = block.lower()
        if title and block.strip() == title.strip():
            seen_title = True
            continue
        if lowered in {"federal reserve board", "board of governors of the federal reserve system"}:
            continue
        if "last update" in lowered or "return to text" in lowered or "back to top" in lowered:
            break
        if lowered.startswith("share") or lowered.startswith("facebook") or lowered.startswith("post"):
            continue
        if not seen_title and len(block.split()) <= 3 and any(month in lowered for month in [
            "january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december"
        ]):
            continue
        filtered.append(block)

    refined = "\n\n".join(filtered)
    return refined if len(refined) >= 120 else text


def _suppress_boilerplate_blocks(
    text: str,
    document_type: DocumentType,
    source: Optional[str] = None,
    speaker_name: Optional[str] = None,
) -> str:
    patterns = list(BOILERPLATE_PATTERNS.get(document_type, []))
    if source:
        patterns.extend((SOURCE_BOILERPLATE_PATTERNS.get(source, {})).get(document_type, []))
    if speaker_name:
        patterns.extend((SPEAKER_BOILERPLATE_PATTERNS.get(speaker_name, {})).get(document_type, []))
    if not patterns:
        return text

    kept: List[str] = []
    for block in [block.strip() for block in text.split("\n\n") if block.strip()]:
        if any(pattern.search(block) for pattern in patterns):
            continue
        kept.append(block)

    suppressed = "\n\n".join(kept)
    return suppressed if kept else text


def _pdf_to_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    pages = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        if extracted.strip():
            pages.append(extracted)
    return _clean_text("\n\n".join(pages))


def _segment_text(text: str, speaker_name: Optional[str]) -> List[DocumentSegment]:
    segments: List[DocumentSegment] = []
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    for index, block in enumerate(blocks):
        lowered = block.lower()
        segment_type = SegmentType.BODY
        current_speaker = speaker_name
        if Q_PREFIX.match(lowered):
            segment_type = SegmentType.QUESTION
            current_speaker = "Question"
        elif A_PREFIX.match(lowered):
            segment_type = SegmentType.ANSWER
        segments.append(
            DocumentSegment(
                segment_index=index,
                speaker_name=current_speaker,
                segment_type=segment_type,
                text=block,
            )
        )
    return segments


def normalize_url(url: str, timeout: int = 30) -> NormalizedDocument:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    content_type_header = response.headers.get("Content-Type", "")
    if url.lower().endswith(".pdf") or "application/pdf" in content_type_header:
        text = _pdf_to_text(response.content)
        soup = None
        content_type = ContentType.PDF
    else:
        config = _site_config(url)
        text, soup = _html_to_text_for_site(response.content, selectors=(config or {}).get("content_selectors"))
        content_type = ContentType.HTML

    config = _site_config(url)
    title = _extract_title_for_site(soup, url, selectors=(config or {}).get("title_selectors"))
    if content_type == ContentType.HTML and _is_fed_domain(url):
        text = _refine_fed_text(text, title)
    speaker_name = _extract_speaker(text, soup, selectors=(config or {}).get("speaker_selectors"))
    speech_date = _extract_date(text, soup, selectors=(config or {}).get("date_selectors"))
    document_type = _detect_document_type(text, title, url)
    source = _detect_source(url)
    text = _suppress_boilerplate_blocks(text, document_type, source=source, speaker_name=speaker_name)
    source_hash = _hash_text(text)

    return NormalizedDocument(
        document_id=f"doc_{uuid4().hex[:12]}",
        source_url=url,
        source_type="url",
        content_type=content_type,
        title=title,
        speaker_name=speaker_name,
        speech_date=speech_date,
        document_type=document_type,
        source=source,
        normalized_text=text,
        raw_content=response.text if content_type == ContentType.HTML else text,
        segments=_segment_text(text, speaker_name),
        source_metadata={"http_content_type": content_type_header},
        source_hash=source_hash,
    )


def normalize_markdown(markdown_text: str, metadata: Optional[Dict[str, str]] = None) -> NormalizedDocument:
    metadata = metadata or {}
    text = _clean_text(markdown_text)
    title = metadata.get("title")
    speaker_name = metadata.get("speaker_name") or _extract_speaker(text, None)
    source_url = metadata.get("source_url")
    speech_date = None
    if metadata.get("speech_date"):
        speech_date = date.fromisoformat(metadata["speech_date"])
    else:
        speech_date = _extract_date(text, None)

    document_type_value = metadata.get("document_type")
    if document_type_value and document_type_value in DocumentType._value2member_map_:
        document_type = DocumentType(document_type_value)
    else:
        document_type = _detect_document_type(text, title, source_url)

    text = _suppress_boilerplate_blocks(
        text,
        document_type,
        source=metadata.get("source"),
        speaker_name=speaker_name,
    )
    source_hash = _hash_text(text)

    return NormalizedDocument(
        document_id=f"doc_{uuid4().hex[:12]}",
        source_url=source_url,
        source_type="markdown",
        content_type=ContentType.MARKDOWN,
        title=title,
        speaker_name=speaker_name,
        speech_date=speech_date,
        document_type=document_type,
        source=metadata.get("source"),
        normalized_text=text,
        raw_markdown=markdown_text,
        segments=_segment_text(text, speaker_name),
        source_metadata=metadata,
        source_hash=source_hash,
    )
