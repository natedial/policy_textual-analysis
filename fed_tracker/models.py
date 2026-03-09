from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    SPEECH = "speech"
    PREPARED_REMARKS = "prepared_remarks"
    PRESS_RELEASE = "press_release"
    PRESS_CONFERENCE = "press_conference"
    QA_TRANSCRIPT = "qa_transcript"
    INTERVIEW = "interview"
    TESTIMONY = "testimony"
    STATEMENT = "statement"
    COMMENT = "comment"
    UNKNOWN = "unknown"


class ContentType(str, Enum):
    HTML = "html"
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    UNKNOWN = "unknown"


class SegmentType(str, Enum):
    BODY = "body"
    QUESTION = "question"
    ANSWER = "answer"
    HEADER = "header"
    FOOTER = "footer"
    UNKNOWN = "unknown"


class ComparisonType(str, Enum):
    T_MINUS_1 = "t_minus_1"
    WINDOW_75D = "window_75d"
    WINDOW_24M = "window_24m"


class EvidenceQuote(BaseModel):
    quote: str
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    source: Optional[str] = None


class DocumentSegment(BaseModel):
    segment_index: int
    speaker_name: Optional[str] = None
    segment_type: SegmentType = SegmentType.BODY
    text: str


class PhraseSignal(BaseModel):
    phrase_text: str
    normalized_phrase: str
    semantic_key: str
    current_count: int = 1
    historical_count: int = 0
    rarity_score: float = 0.0
    examples: List[str] = Field(default_factory=list)


class ThemeAssessment(BaseModel):
    stance: str
    trajectory: str
    emphasis_score: int = Field(ge=1, le=10)
    hedging_level: str
    key_hedges: List[str] = Field(default_factory=list)
    confidence: str
    uncertainty: str = "medium"
    evidence: List[EvidenceQuote] = Field(default_factory=list)


class NormalizedDocument(BaseModel):
    document_id: str
    source_url: Optional[str] = None
    source_type: str = "url"
    content_type: ContentType = ContentType.UNKNOWN
    title: Optional[str] = None
    speaker_name: Optional[str] = None
    speech_date: Optional[date] = None
    document_type: DocumentType = DocumentType.UNKNOWN
    source: Optional[str] = None
    normalized_text: str
    raw_content: Optional[str] = None
    raw_markdown: Optional[str] = None
    segments: List[DocumentSegment] = Field(default_factory=list)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)
    source_hash: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SemanticFingerprint(BaseModel):
    document_id: str
    speaker_name: Optional[str] = None
    speech_date: Optional[date] = None
    document_type: DocumentType = DocumentType.UNKNOWN
    themes: Dict[str, ThemeAssessment] = Field(default_factory=dict)
    emergent_themes: List[str] = Field(default_factory=list)
    phrase_signals: List[PhraseSignal] = Field(default_factory=list)
    overall_tone: str = ""
    uncertainty_notes: List[str] = Field(default_factory=list)
    prompt_version: str = "v2"
    model_version: str = "heuristic"
    raw_llm_response: Optional[str] = None


class ThemeChange(BaseModel):
    theme: str
    change_type: str
    strength: str
    uncertainty: str
    before: Optional[ThemeAssessment] = None
    after: Optional[ThemeAssessment] = None
    evidence_before: List[EvidenceQuote] = Field(default_factory=list)
    evidence_after: List[EvidenceQuote] = Field(default_factory=list)
    summary: str


class ComparisonResult(BaseModel):
    comparison_id: str
    speaker_name: Optional[str] = None
    target_document_id: str
    base_document_id: Optional[str] = None
    comparison_type: ComparisonType = ComparisonType.T_MINUS_1
    window_days: Optional[int] = None
    theme_changes: List[ThemeChange] = Field(default_factory=list)
    orphaned_concepts: List[str] = Field(default_factory=list)
    new_themes: List[str] = Field(default_factory=list)
    phrase_anomalies: List[PhraseSignal] = Field(default_factory=list)
    summary: str = ""
    uncertainty_notes: List[str] = Field(default_factory=list)


class AnalysisRun(BaseModel):
    run_id: str
    analysis_type: str
    target_id: str
    prompt_version: Optional[str] = None
    model_version: Optional[str] = None
    input_hash: Optional[str] = None
    raw_output: Optional[str] = None
    parsed_output: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
