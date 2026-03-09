"""Database client for the V1 Fed textual change tracker schema."""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv
from supabase import Client, create_client

from fed_tracker.models import AnalysisRun, ComparisonResult, NormalizedDocument, SemanticFingerprint

load_dotenv()


class Database:
    def __init__(self, supabase_url: str | None = None, supabase_key: str | None = None):
        self.url = supabase_url or os.getenv("SUPABASE_URL")
        self.key = supabase_key or os.getenv("SUPABASE_KEY")
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
        self.client: Client = create_client(self.url, self.key)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _speaker_key(self, name: str) -> str:
        key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return key or "unknown_speaker"

    def _select_one(self, table: str, **filters: Any) -> Optional[Dict[str, Any]]:
        query = self.client.table(table).select("*")
        for field, value in filters.items():
            query = query.eq(field, value)
        result = query.limit(1).execute()
        return result.data[0] if result.data else None

    # ---------------------------------------------------------------------
    # Speakers
    # ---------------------------------------------------------------------

    def get_or_create_speaker(
        self,
        name: str,
        title: str | None = None,
        institution: str | None = None,
        is_fomc_member: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        speaker_key = self._speaker_key(name)
        existing = self._select_one("speakers", speaker_key=speaker_key)
        if existing:
            return existing["id"]

        result = self.client.table("speakers").insert(
            {
                "speaker_key": speaker_key,
                "name": name,
                "title": title,
                "institution": institution,
                "is_fomc_member": is_fomc_member,
                "metadata": metadata or {},
            }
        ).execute()
        return result.data[0]["id"]

    # ---------------------------------------------------------------------
    # Documents
    # ---------------------------------------------------------------------

    def insert_source_document(
        self,
        source_url: str | None,
        source_type: str,
        content_type: str,
        source_hash: str,
        raw_content: str | None = None,
        raw_markdown: str | None = None,
        fetch_metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        existing = self._select_one("source_documents", source_hash=source_hash)
        if existing:
            return existing["id"]

        result = self.client.table("source_documents").insert(
            {
                "source_url": source_url,
                "source_type": source_type,
                "content_type": content_type,
                "raw_content": raw_content,
                "raw_markdown": raw_markdown,
                "source_hash": source_hash,
                "fetch_metadata": fetch_metadata or {},
            }
        ).execute()
        return result.data[0]["id"]

    def insert_document(
        self,
        document: NormalizedDocument,
        speaker_title: str | None = None,
        speaker_institution: str | None = None,
        is_fomc_member: bool = False,
        source_document_id: int | None = None,
    ) -> int:
        existing = self._select_one("documents", document_key=document.document_id)
        if existing:
            return existing["id"]

        speaker_id = None
        if document.speaker_name:
            speaker_id = self.get_or_create_speaker(
                document.speaker_name,
                title=speaker_title,
                institution=speaker_institution,
                is_fomc_member=is_fomc_member,
            )

        result = self.client.table("documents").insert(
            {
                "document_key": document.document_id,
                "source_document_id": source_document_id,
                "speaker_id": speaker_id,
                "speaker_name": document.speaker_name,
                "title": document.title,
                "speech_date": document.speech_date.isoformat() if document.speech_date else None,
                "document_type": document.document_type.value,
                "source": document.source,
                "content_type": document.content_type.value,
                "normalized_text": document.normalized_text,
                "source_hash": document.source_hash,
                "source_metadata": document.source_metadata,
                "word_count": len(document.normalized_text.split()),
            }
        ).execute()
        document_id = result.data[0]["id"]

        if document.segments:
            rows = [
                {
                    "document_id": document_id,
                    "segment_index": segment.segment_index,
                    "speaker_name": segment.speaker_name,
                    "segment_type": segment.segment_type.value,
                    "text": segment.text,
                }
                for segment in document.segments
            ]
            self.client.table("document_segments").insert(rows).execute()

        return document_id

    def get_latest_document_for_speaker(
        self,
        speaker_name: str,
        exclude_document_key: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        query = (
            self.client.table("documents")
            .select("*")
            .eq("speaker_name", speaker_name)
            .order("speech_date", desc=True)
            .order("created_at", desc=True)
        )
        result = query.limit(25).execute()
        for row in result.data:
            if exclude_document_key and row.get("document_key") == exclude_document_key:
                continue
            return row
        return None

    def get_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        return self._select_one("documents", id=document_id)

    def get_document_by_key(self, document_key: str) -> Optional[Dict[str, Any]]:
        return self._select_one("documents", document_key=document_key)

    def get_document_segments(self, document_id: int) -> List[Dict[str, Any]]:
        result = (
            self.client.table("document_segments")
            .select("*")
            .eq("document_id", document_id)
            .order("segment_index")
            .execute()
        )
        return result.data

    def get_documents_for_speaker(
        self,
        speaker_name: str,
        before_date: Optional[date] = None,
        within_days: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = (
            self.client.table("documents")
            .select("*")
            .eq("speaker_name", speaker_name)
            .order("speech_date", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
        )
        result = query.execute()
        rows = result.data
        if before_date:
            rows = [row for row in rows if row.get("speech_date") and row["speech_date"] < before_date.isoformat()]
        if before_date and within_days:
            floor = before_date - timedelta(days=within_days)
            rows = [row for row in rows if row.get("speech_date") and row["speech_date"] >= floor.isoformat()]
        return rows

    def get_context_documents(
        self,
        speaker_name: str,
        before_date: Optional[date] = None,
        within_days: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return self.get_documents_for_speaker(
            speaker_name=speaker_name,
            before_date=before_date,
            within_days=within_days,
            limit=limit,
        )

    # ---------------------------------------------------------------------
    # Analysis artifacts
    # ---------------------------------------------------------------------

    def insert_analysis_run(self, run: AnalysisRun) -> int:
        existing = self._select_one("analysis_runs", run_key=run.run_id)
        if existing:
            return existing["id"]

        result = self.client.table("analysis_runs").insert(
            {
                "run_key": run.run_id,
                "analysis_type": run.analysis_type,
                "target_type": "document",
                "target_id": run.target_id,
                "prompt_version": run.prompt_version,
                "model_version": run.model_version,
                "input_hash": run.input_hash,
                "raw_output": run.raw_output,
                "parsed_output": run.parsed_output,
            }
        ).execute()
        return result.data[0]["id"]

    def insert_fingerprint(
        self,
        fingerprint: SemanticFingerprint,
        document_id: int,
        analysis_run_id: int | None = None,
    ) -> int:
        existing = (
            self.client.table("fingerprints")
            .select("id")
            .eq("document_id", document_id)
            .eq("prompt_version", fingerprint.prompt_version)
            .eq("model_version", fingerprint.model_version)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]["id"]

        result = self.client.table("fingerprints").insert(
            {
                "document_id": document_id,
                "analysis_run_id": analysis_run_id,
                "prompt_version": fingerprint.prompt_version,
                "model_version": fingerprint.model_version,
                "themes": {name: value.model_dump() for name, value in fingerprint.themes.items()},
                "emergent_themes": fingerprint.emergent_themes,
                "phrase_signals": [signal.model_dump() for signal in fingerprint.phrase_signals],
                "overall_tone": fingerprint.overall_tone,
                "uncertainty_notes": fingerprint.uncertainty_notes,
                "raw_llm_response": fingerprint.raw_llm_response,
            }
        ).execute()
        fingerprint_id = result.data[0]["id"]

        if fingerprint.phrase_signals:
            speaker_id = None
            if fingerprint.speaker_name:
                speaker = self._select_one("speakers", speaker_key=self._speaker_key(fingerprint.speaker_name))
                speaker_id = speaker["id"] if speaker else None
            self.client.table("phrase_observations").insert(
                [
                    {
                        "document_id": document_id,
                        "speaker_id": speaker_id,
                        "phrase_text": signal.phrase_text,
                        "normalized_phrase": signal.normalized_phrase,
                        "semantic_key": signal.semantic_key,
                        "current_count": signal.current_count,
                        "historical_count": signal.historical_count,
                        "rarity_score": signal.rarity_score,
                        "examples": signal.examples,
                    }
                    for signal in fingerprint.phrase_signals
                ]
            ).execute()

        return fingerprint_id

    def get_latest_fingerprint_for_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        result = (
            self.client.table("fingerprints")
            .select("*")
            .eq("document_id", document_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_fingerprint_for_document(
        self,
        document_id: int,
        prompt_version: str | None = None,
        model_version: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        query = self.client.table("fingerprints").select("*").eq("document_id", document_id)
        if prompt_version:
            query = query.eq("prompt_version", prompt_version)
        if model_version:
            query = query.eq("model_version", model_version)
        result = query.order("created_at", desc=True).limit(1).execute()
        return result.data[0] if result.data else None

    def insert_comparison_result(
        self,
        comparison: ComparisonResult,
        target_document_id: int,
        target_fingerprint_id: int,
        base_document_id: int | None = None,
        base_fingerprint_id: int | None = None,
    ) -> int:
        existing = self._select_one("comparison_results", comparison_key=comparison.comparison_id)
        if existing:
            return existing["id"]

        speaker_id = None
        if comparison.speaker_name:
            speaker = self._select_one("speakers", speaker_key=self._speaker_key(comparison.speaker_name))
            speaker_id = speaker["id"] if speaker else None

        result = self.client.table("comparison_results").insert(
            {
                "comparison_key": comparison.comparison_id,
                "speaker_id": speaker_id,
                "speaker_name": comparison.speaker_name,
                "base_document_id": base_document_id,
                "target_document_id": target_document_id,
                "base_fingerprint_id": base_fingerprint_id,
                "target_fingerprint_id": target_fingerprint_id,
                "comparison_type": comparison.comparison_type.value,
                "window_days": comparison.window_days,
                "theme_changes": [change.model_dump() for change in comparison.theme_changes],
                "orphaned_concepts": comparison.orphaned_concepts,
                "new_themes": comparison.new_themes,
                "phrase_anomalies": [signal.model_dump() for signal in comparison.phrase_anomalies],
                "summary": comparison.summary,
                "uncertainty_notes": comparison.uncertainty_notes,
            }
        ).execute()
        return result.data[0]["id"]

    # ---------------------------------------------------------------------
    # Compatibility helpers for old naming
    # ---------------------------------------------------------------------

    def speech_exists(self, url: str) -> bool:
        result = self.client.table("source_documents").select("id").eq("source_url", url).limit(1).execute()
        return bool(result.data)

    def source_document_exists(self, source_url: str) -> bool:
        return self.speech_exists(source_url)

    def get_recent_documents_with_fingerprints(self, limit: int = 10) -> List[Dict[str, Any]]:
        result = self.client.table("recent_documents_with_fingerprints").select("*").limit(limit).execute()
        return result.data

    def get_recent_comparisons(
        self,
        speaker_name: str | None = None,
        comparison_type: str | None = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = self.client.table("comparison_results").select("*").order("created_at", desc=True).limit(limit)
        if speaker_name:
            query = query.eq("speaker_name", speaker_name)
        if comparison_type:
            query = query.eq("comparison_type", comparison_type)
        return query.execute().data

    def get_phrase_observations(
        self,
        speaker_name: str,
        limit: int = 25,
        min_rarity: float | None = None,
    ) -> List[Dict[str, Any]]:
        query = (
            self.client.table("phrase_observations")
            .select("*, documents!inner(speaker_name, speech_date, title)")
            .eq("documents.speaker_name", speaker_name)
            .order("rarity_score", desc=True)
            .limit(limit)
        )
        rows = query.execute().data
        if min_rarity is not None:
            rows = [row for row in rows if (row.get("rarity_score") or 0) >= min_rarity]
        return rows

    def get_recent_document_for_speaker(self, speaker_name: str) -> Optional[Dict[str, Any]]:
        rows = self.get_documents_for_speaker(speaker_name=speaker_name, limit=1)
        return rows[0] if rows else None


if __name__ == "__main__":
    db = Database()
    print("Database connection successful")
    recent = db.get_recent_documents_with_fingerprints(limit=5)
    print(f"Found {len(recent)} recent documents")
