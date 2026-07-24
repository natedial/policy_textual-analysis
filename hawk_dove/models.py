from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


Direction = Literal["hawkish", "dovish", "neutral"]


class HawkDoveEvidence(BaseModel):
    quote: str
    direction: Direction = "neutral"
    weight: float = Field(ge=0.0, le=1.0, default=0.5)
    start_char: Optional[int] = None
    end_char: Optional[int] = None


class SectionScore(BaseModel):
    section_id: str
    label: str = ""
    overall_score: float = Field(ge=0.0, le=10.0)
    inflation_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    labor_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    growth_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    policy_action_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    rationale: str = ""
    evidence: List[HawkDoveEvidence] = Field(default_factory=list)


class HawkDoveScoreResult(BaseModel):
    overall_score: float = Field(ge=0.0, le=10.0)
    inflation_score: float = Field(ge=0.0, le=10.0)
    labor_score: float = Field(ge=0.0, le=10.0)
    growth_score: float = Field(ge=0.0, le=10.0)
    policy_action_score: float = Field(ge=0.0, le=10.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence: List[HawkDoveEvidence] = Field(default_factory=list)
    insufficient_policy_content: bool = False
    section_scores: List[SectionScore] = Field(default_factory=list)


class HawkDoveObservation(BaseModel):
    score_key: str = Field(default_factory=lambda: str(uuid4()))
    document_key: str
    document_id: Optional[int] = None
    speaker_name: Optional[str] = None
    speech_date: Optional[date] = None
    document_type: Optional[str] = None
    source_url: Optional[str] = None
    source_hash: str
    title: Optional[str] = None
    institution: Optional[str] = None
    role: Optional[str] = None
    was_voter_as_of_date: Optional[bool] = None
    was_fomc_participant_as_of_date: Optional[bool] = None
    score: HawkDoveScoreResult
    prompt_version: str
    model_version: str
    model_parameters: Dict[str, Any] = Field(default_factory=dict)
    extraction_version: str = "v1"
    calibration_version: str = "none"
    scored_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    manual_override: bool = False
    override_notes: Optional[str] = None

    def to_export_row(self) -> Dict[str, Any]:
        score = self.score
        return {
            "score_key": self.score_key,
            "document_key": self.document_key,
            "speaker_name": self.speaker_name,
            "speech_date": self.speech_date.isoformat() if self.speech_date else None,
            "document_type": self.document_type,
            "source_url": self.source_url,
            "source_hash": self.source_hash,
            "title": self.title,
            "institution": self.institution,
            "role": self.role,
            "overall_score": None if score.insufficient_policy_content else score.overall_score,
            "inflation_score": None if score.insufficient_policy_content else score.inflation_score,
            "labor_score": None if score.insufficient_policy_content else score.labor_score,
            "growth_score": None if score.insufficient_policy_content else score.growth_score,
            "policy_action_score": None if score.insufficient_policy_content else score.policy_action_score,
            "confidence": score.confidence,
            "rationale": score.rationale,
            "evidence_json": [item.model_dump() for item in score.evidence],
            "insufficient_policy_content": score.insufficient_policy_content,
            "was_voter_as_of_date": self.was_voter_as_of_date,
            "was_fomc_participant_as_of_date": self.was_fomc_participant_as_of_date,
            "prompt_version": self.prompt_version,
            "model_version": self.model_version,
            "calibration_version": self.calibration_version,
            "scored_at": self.scored_at.isoformat(),
        }


class OfficialAggregate(BaseModel):
    speaker_name: str
    as_of_date: date
    method: str
    window_days: int
    half_life_days: Optional[float] = None
    overall_score: Optional[float] = None
    inflation_score: Optional[float] = None
    labor_score: Optional[float] = None
    growth_score: Optional[float] = None
    policy_action_score: Optional[float] = None
    communication_count: int = 0
    coverage_notes: Dict[str, Any] = Field(default_factory=dict)
    score_keys: List[str] = Field(default_factory=list)
    was_voter: Optional[bool] = None
    was_fomc_participant: Optional[bool] = None


class CommitteeAggregate(BaseModel):
    as_of_date: date
    cohort: str
    method: str
    window_days: int
    half_life_days: Optional[float] = None
    overall_score: Optional[float] = None
    official_count: int = 0
    communication_count: int = 0
    coverage_notes: Dict[str, Any] = Field(default_factory=dict)
    official_scores: List[OfficialAggregate] = Field(default_factory=list)


class MembershipRecord(BaseModel):
    speaker_key: str
    name: str
    calendar_year: int
    role: str
    institution: str
    is_fomc_participant: bool = True
    is_voting_member: bool = False
    effective_start: Optional[date] = None
    effective_end: Optional[date] = None
    name_variants: List[str] = Field(default_factory=list)
    term_start: Optional[date] = None
    term_end: Optional[date] = None
