from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

from fed_tracker.comparison import compare_fingerprints, summarize_window
from fed_tracker.extraction import AnthropicFingerprintExtractor, BaseFingerprintExtractor, HeuristicFingerprintExtractor
from fed_tracker.models import AnalysisRun, ComparisonResult, ComparisonType, NormalizedDocument, SemanticFingerprint
from fed_tracker.normalization import normalize_markdown, normalize_url
from fed_tracker.storage import document_from_record, fingerprint_from_record

try:
    from db import Database
except ImportError:  # pragma: no cover - import is optional for local-only use
    Database = None  # type: ignore[assignment]


@dataclass
class AnalysisBundle:
    document: NormalizedDocument
    fingerprint: SemanticFingerprint


@dataclass
class PersistedBundle:
    source_document_id: int
    document_id: int
    fingerprint_id: int
    analysis_run_id: int


@dataclass
class StoredAnalysisResult:
    bundle: AnalysisBundle
    persisted: Optional[PersistedBundle] = None
    comparisons: Dict[str, ComparisonResult] = field(default_factory=dict)
    context_summaries: Dict[str, str] = field(default_factory=dict)


class AnalysisPipeline:
    def __init__(self, extractor: Optional[BaseFingerprintExtractor] = None, database: Optional[Database] = None):
        self.extractor = extractor or self._default_extractor()
        self.database = database

    def _default_extractor(self) -> BaseFingerprintExtractor:
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                return AnthropicFingerprintExtractor()
            except Exception:
                pass
        return HeuristicFingerprintExtractor()

    def analyze_url(
        self,
        url: str,
        historical_documents: Optional[Sequence[NormalizedDocument]] = None,
    ) -> AnalysisBundle:
        document = normalize_url(url)
        return self.analyze_document(document, historical_documents=historical_documents)

    def analyze_markdown(
        self,
        markdown_text: str,
        metadata: Optional[dict] = None,
        historical_documents: Optional[Sequence[NormalizedDocument]] = None,
    ) -> AnalysisBundle:
        document = normalize_markdown(markdown_text, metadata=metadata)
        return self.analyze_document(document, historical_documents=historical_documents)

    def analyze_document(
        self,
        document: NormalizedDocument,
        historical_documents: Optional[Sequence[NormalizedDocument]] = None,
    ) -> AnalysisBundle:
        if historical_documents is None and self.database:
            historical_documents = [bundle.document for bundle in self._load_history_from_db(document, within_days=730)]
        historical_documents = list(historical_documents or [])
        historical_texts = [item.normalized_text for item in historical_documents]
        try:
            fingerprint = self.extractor.extract(document, historical_texts=historical_texts)
        except Exception as exc:
            if isinstance(self.extractor, HeuristicFingerprintExtractor):
                raise
            fallback = HeuristicFingerprintExtractor()
            fingerprint = fallback.extract(document, historical_texts=historical_texts)
            fingerprint.uncertainty_notes.append(
                f"Primary extractor failed and heuristic fallback was used: {type(exc).__name__}"
            )
        return AnalysisBundle(document=document, fingerprint=fingerprint)

    def compare_bundles(
        self,
        base_bundle: Optional[AnalysisBundle],
        target_bundle: AnalysisBundle,
        context_bundles: Optional[Iterable[AnalysisBundle]] = None,
        comparison_type: ComparisonType = ComparisonType.T_MINUS_1,
        window_days: Optional[int] = None,
    ) -> ComparisonResult:
        context_fingerprints = [bundle.fingerprint for bundle in (context_bundles or [])]
        return compare_fingerprints(
            base=base_bundle.fingerprint if base_bundle else None,
            target=target_bundle.fingerprint,
            context_fingerprints=context_fingerprints,
            comparison_type=comparison_type,
            window_days=window_days,
        )

    def summarize_context(self, bundles: Iterable[AnalysisBundle], window_label: str) -> str:
        return summarize_window((bundle.fingerprint for bundle in bundles), window_label)

    def analyze_and_store_url(self, url: str) -> StoredAnalysisResult:
        bundle = self.analyze_url(url)
        return self.store_bundle_with_comparisons(bundle)

    def analyze_and_store_markdown(self, markdown_text: str, metadata: Optional[dict] = None) -> StoredAnalysisResult:
        bundle = self.analyze_markdown(markdown_text, metadata=metadata)
        return self.store_bundle_with_comparisons(bundle)

    def store_bundle_with_comparisons(self, bundle: AnalysisBundle) -> StoredAnalysisResult:
        persisted = self.persist_bundle(bundle) if self.database else None
        result = StoredAnalysisResult(bundle=bundle, persisted=persisted)

        if not self.database or not bundle.document.speaker_name:
            return result

        history = self._load_history_from_db(bundle.document, within_days=730)
        history = [item for item in history if item.document.document_id != bundle.document.document_id]
        if not history:
            return result

        baseline = history[0]
        result.comparisons[ComparisonType.T_MINUS_1.value] = self.compare_bundles(
            base_bundle=baseline,
            target_bundle=bundle,
            context_bundles=history,
            comparison_type=ComparisonType.T_MINUS_1,
        )

        history_75d = self._filter_history(history, bundle.document, 75)
        result.context_summaries[ComparisonType.WINDOW_75D.value] = self.summarize_context(history_75d, "75d")
        result.context_summaries[ComparisonType.WINDOW_24M.value] = self.summarize_context(history, "24m")

        result.comparisons[ComparisonType.WINDOW_75D.value] = self.compare_bundles(
            base_bundle=baseline,
            target_bundle=bundle,
            context_bundles=history_75d,
            comparison_type=ComparisonType.WINDOW_75D,
            window_days=75,
        )
        result.comparisons[ComparisonType.WINDOW_24M.value] = self.compare_bundles(
            base_bundle=baseline,
            target_bundle=bundle,
            context_bundles=history,
            comparison_type=ComparisonType.WINDOW_24M,
            window_days=730,
        )

        if persisted:
            baseline_record = self.database.get_document_by_key(baseline.document.document_id)
            baseline_fingerprint_record = (
                self.database.get_fingerprint_for_document(baseline_record["id"]) if baseline_record else None
            )
            base_document_id = baseline_record["id"] if baseline_record else None
            base_fingerprint_id = baseline_fingerprint_record["id"] if baseline_fingerprint_record else None
            for comparison in result.comparisons.values():
                self.database.insert_comparison_result(
                    comparison=comparison,
                    target_document_id=persisted.document_id,
                    target_fingerprint_id=persisted.fingerprint_id,
                    base_document_id=base_document_id,
                    base_fingerprint_id=base_fingerprint_id,
                )

        return result

    def persist_bundle(self, bundle: AnalysisBundle) -> PersistedBundle:
        if not self.database:
            raise RuntimeError("A database client is required to persist analysis bundles")

        source_document_id = self.database.insert_source_document(
            source_url=bundle.document.source_url,
            source_type=bundle.document.source_type,
            content_type=bundle.document.content_type.value,
            source_hash=bundle.document.source_hash,
            raw_content=bundle.document.raw_content,
            raw_markdown=bundle.document.raw_markdown,
            fetch_metadata=bundle.document.source_metadata,
        )
        document_id = self.database.insert_document(bundle.document, source_document_id=source_document_id)
        analysis_run = AnalysisRun(
            run_id=f"run_{uuid4().hex[:12]}",
            analysis_type="fingerprint_extraction",
            target_id=bundle.document.document_id,
            prompt_version=bundle.fingerprint.prompt_version,
            model_version=bundle.fingerprint.model_version,
            input_hash=bundle.document.source_hash,
            raw_output=bundle.fingerprint.raw_llm_response,
            parsed_output=bundle.fingerprint.model_dump(mode="json"),
        )
        analysis_run_id = self.database.insert_analysis_run(analysis_run)
        fingerprint_id = self.database.insert_fingerprint(bundle.fingerprint, document_id, analysis_run_id)
        return PersistedBundle(
            source_document_id=source_document_id,
            document_id=document_id,
            fingerprint_id=fingerprint_id,
            analysis_run_id=analysis_run_id,
        )

    def _load_history_from_db(
        self,
        document: NormalizedDocument,
        within_days: int,
        limit: int = 100,
    ) -> List[AnalysisBundle]:
        if not self.database or not document.speaker_name:
            return []
        rows = self.database.get_documents_for_speaker(
            speaker_name=document.speaker_name,
            before_date=document.speech_date,
            within_days=within_days if document.speech_date else None,
            limit=limit,
        )
        bundles: List[AnalysisBundle] = []
        for row in rows:
            bundle = self._hydrate_bundle_from_db_record(row)
            if bundle:
                bundles.append(bundle)
        return bundles

    def _hydrate_bundle_from_db_record(self, document_row: dict) -> Optional[AnalysisBundle]:
        if not self.database:
            return None
        fingerprint_row = self.database.get_fingerprint_for_document(document_row["id"])
        if not fingerprint_row:
            return None
        segments = self.database.get_document_segments(document_row["id"])
        document = document_from_record(document_row, segments=segments)
        fingerprint = fingerprint_from_record(fingerprint_row, document)
        return AnalysisBundle(document=document, fingerprint=fingerprint)

    def _filter_history(
        self,
        history: Sequence[AnalysisBundle],
        document: NormalizedDocument,
        window_days: int,
    ) -> List[AnalysisBundle]:
        if not document.speech_date:
            return list(history)
        floor = document.speech_date.toordinal() - window_days
        return [
            item for item in history
            if item.document.speech_date and item.document.speech_date.toordinal() >= floor
        ]
