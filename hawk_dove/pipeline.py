"""Orchestration for hawk–dove scoring on normalized documents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence
from uuid import uuid4

from fed_tracker.models import AnalysisRun, NormalizedDocument
from fed_tracker.normalization import normalize_markdown, normalize_url
from hawk_dove.models import HawkDoveObservation
from hawk_dove.officials import OfficialsDirectory
from hawk_dove.scoring import (
    EXTRACTION_VERSION,
    BaseHawkDoveScorer,
    HeuristicHawkDoveScorer,
    default_scorer,
)

try:
    from db import Database
except ImportError:  # pragma: no cover
    Database = None  # type: ignore[assignment]


@dataclass
class ScoredDocument:
    document: NormalizedDocument
    observation: HawkDoveObservation
    persisted_score_id: Optional[int] = None
    analysis_run_id: Optional[int] = None


class HawkDovePipeline:
    def __init__(
        self,
        scorer: Optional[BaseHawkDoveScorer] = None,
        officials: Optional[OfficialsDirectory] = None,
        database: Optional["Database"] = None,
    ):
        self.scorer = scorer or default_scorer()
        self.officials = officials or OfficialsDirectory()
        self.database = database

    def score_document(self, document: NormalizedDocument, persist: bool = False) -> ScoredDocument:
        score = self.scorer.score(document)
        membership, was_voter, was_participant = self.officials.resolve(
            document.speaker_name,
            document.speech_date,
        )
        observation = HawkDoveObservation(
            document_key=document.document_id,
            speaker_name=document.speaker_name,
            speech_date=document.speech_date,
            document_type=document.document_type.value if document.document_type else None,
            source_url=document.source_url,
            source_hash=document.source_hash,
            title=document.title,
            institution=membership.institution if membership else document.source,
            role=membership.role if membership else None,
            was_voter_as_of_date=was_voter,
            was_fomc_participant_as_of_date=was_participant,
            score=score,
            prompt_version=self.scorer.prompt_version,
            model_version=self.scorer.model_version,
            model_parameters=dict(getattr(self.scorer, "model_parameters", {}) or {}),
            extraction_version=EXTRACTION_VERSION,
            calibration_version="none",
        )

        persisted_score_id = None
        analysis_run_id = None
        if persist and self.database:
            persisted_score_id, analysis_run_id = self._persist(document, observation)

        return ScoredDocument(
            document=document,
            observation=observation,
            persisted_score_id=persisted_score_id,
            analysis_run_id=analysis_run_id,
        )

    def score_url(self, url: str, persist: bool = False) -> ScoredDocument:
        return self.score_document(normalize_url(url), persist=persist)

    def score_markdown(
        self,
        markdown_text: str,
        metadata: Optional[dict] = None,
        persist: bool = False,
    ) -> ScoredDocument:
        return self.score_document(normalize_markdown(markdown_text, metadata=metadata or {}), persist=persist)

    def score_urls(self, urls: Sequence[str], persist: bool = False) -> List[ScoredDocument]:
        return [self.score_url(url, persist=persist) for url in urls]

    def _persist(self, document: NormalizedDocument, observation: HawkDoveObservation) -> tuple[int, int]:
        assert self.database is not None
        source_document_id = self.database.insert_source_document(
            source_url=document.source_url,
            source_type=document.source_type,
            content_type=document.content_type.value,
            source_hash=document.source_hash,
            raw_content=document.raw_content,
            raw_markdown=document.raw_markdown,
            fetch_metadata=document.source_metadata,
        )
        document_id = self.database.insert_document(
            document,
            speaker_title=observation.role,
            speaker_institution=observation.institution,
            is_fomc_member=bool(observation.was_fomc_participant_as_of_date),
            source_document_id=source_document_id,
        )
        observation.document_id = document_id

        run = AnalysisRun(
            run_id=str(uuid4()),
            analysis_type="hawk_dove_score",
            target_id=document.document_id,
            prompt_version=observation.prompt_version,
            model_version=observation.model_version,
            input_hash=document.source_hash,
            raw_output=None,
            parsed_output=observation.score.model_dump(mode="json"),
        )
        analysis_run_id = self.database.insert_analysis_run(run)
        score_id = self.database.insert_hawk_dove_score(observation, document_id=document_id, analysis_run_id=analysis_run_id)
        return score_id, analysis_run_id


def build_pipeline(persist: bool = False, method: str | None = None) -> HawkDovePipeline:
    database = None
    if persist and Database is not None and os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
        database = Database()
    if method:
        from hawk_dove.registry import get_scorer

        scorer = get_scorer(method)
    else:
        scorer = default_scorer()
    return HawkDovePipeline(scorer=scorer, database=database)
