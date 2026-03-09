from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from fed_tracker.models import (
    AnalysisRun,
    ComparisonResult,
    ComparisonType,
    ContentType,
    DocumentSegment,
    DocumentType,
    EvidenceQuote,
    NormalizedDocument,
    PhraseSignal,
    SemanticFingerprint,
    SegmentType,
    ThemeAssessment,
    ThemeChange,
)


UNCERTAINTY_DEFAULT = "medium"


def _parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _enum_value(enum_cls, value, default):
    try:
        return enum_cls(value)
    except Exception:
        return default


def _evidence_list(items: Optional[Iterable[Dict[str, Any]]]) -> List[EvidenceQuote]:
    return [EvidenceQuote(**item) for item in (items or [])]


def _segments(items: Optional[Iterable[Dict[str, Any]]]) -> List[DocumentSegment]:
    results: List[DocumentSegment] = []
    for item in items or []:
        results.append(
            DocumentSegment(
                segment_index=item.get("segment_index", 0),
                speaker_name=item.get("speaker_name"),
                segment_type=_enum_value(SegmentType, item.get("segment_type"), SegmentType.BODY),
                text=item.get("text", ""),
            )
        )
    return results


def document_from_record(record: Dict[str, Any], segments: Optional[Iterable[Dict[str, Any]]] = None) -> NormalizedDocument:
    return NormalizedDocument(
        document_id=record.get("document_key") or record.get("document_id") or record.get("id"),
        source_url=record.get("source_url"),
        source_type=record.get("source_type", "url"),
        content_type=_enum_value(ContentType, record.get("content_type"), ContentType.UNKNOWN),
        title=record.get("title"),
        speaker_name=record.get("speaker_name"),
        speech_date=_parse_date(record.get("speech_date")),
        document_type=_enum_value(DocumentType, record.get("document_type"), DocumentType.UNKNOWN),
        source=record.get("source"),
        normalized_text=record.get("normalized_text", ""),
        raw_content=record.get("raw_content"),
        raw_markdown=record.get("raw_markdown"),
        segments=_segments(segments),
        source_metadata=record.get("source_metadata") or {},
        source_hash=record.get("source_hash") or "",
    )


def fingerprint_from_record(record: Dict[str, Any], document: NormalizedDocument) -> SemanticFingerprint:
    themes = {
        theme_name: ThemeAssessment(
            stance=theme_data["stance"],
            trajectory=theme_data["trajectory"],
            emphasis_score=theme_data["emphasis_score"],
            hedging_level=theme_data["hedging_level"],
            key_hedges=theme_data.get("key_hedges", []),
            confidence=theme_data.get("confidence", "moderate"),
            uncertainty=theme_data.get("uncertainty", UNCERTAINTY_DEFAULT),
            evidence=_evidence_list(theme_data.get("evidence")),
        )
        for theme_name, theme_data in (record.get("themes") or {}).items()
    }

    phrase_signals = [PhraseSignal(**item) for item in (record.get("phrase_signals") or [])]
    return SemanticFingerprint(
        document_id=document.document_id,
        speaker_name=document.speaker_name,
        speech_date=document.speech_date,
        document_type=document.document_type,
        themes=themes,
        emergent_themes=record.get("emergent_themes") or [],
        phrase_signals=phrase_signals,
        overall_tone=record.get("overall_tone") or "",
        uncertainty_notes=record.get("uncertainty_notes") or [],
        prompt_version=record.get("prompt_version") or "v2",
        model_version=record.get("model_version") or "unknown",
        raw_llm_response=record.get("raw_llm_response"),
    )


def comparison_from_record(record: Dict[str, Any]) -> ComparisonResult:
    theme_changes = []
    for item in record.get("theme_changes") or []:
        theme_changes.append(
            ThemeChange(
                theme=item["theme"],
                change_type=item["change_type"],
                strength=item.get("strength", "low"),
                uncertainty=item.get("uncertainty", UNCERTAINTY_DEFAULT),
                before=ThemeAssessment(**item["before"]) if item.get("before") else None,
                after=ThemeAssessment(**item["after"]) if item.get("after") else None,
                evidence_before=_evidence_list(item.get("evidence_before")),
                evidence_after=_evidence_list(item.get("evidence_after")),
                summary=item.get("summary", ""),
            )
        )

    phrase_anomalies = [PhraseSignal(**item) for item in (record.get("phrase_anomalies") or [])]

    return ComparisonResult(
        comparison_id=record.get("comparison_key") or record.get("comparison_id") or record.get("id"),
        speaker_name=record.get("speaker_name"),
        target_document_id=record.get("target_document_key") or str(record.get("target_document_id")),
        base_document_id=record.get("base_document_key") or (str(record.get("base_document_id")) if record.get("base_document_id") else None),
        comparison_type=_enum_value(ComparisonType, record.get("comparison_type"), ComparisonType.T_MINUS_1),
        window_days=record.get("window_days"),
        theme_changes=theme_changes,
        orphaned_concepts=record.get("orphaned_concepts") or [],
        new_themes=record.get("new_themes") or [],
        phrase_anomalies=phrase_anomalies,
        summary=record.get("summary") or "",
        uncertainty_notes=record.get("uncertainty_notes") or [],
    )
