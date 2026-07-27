"""Database client for the V1 Fed textual change tracker schema."""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv
from supabase import Client, create_client

from fed_tracker.models import AnalysisRun, ComparisonResult, NormalizedDocument, SemanticFingerprint

try:
    from hawk_dove.models import CommitteeAggregate, HawkDoveObservation, OfficialAggregate
    from hawk_dove.officials import OfficialsDirectory, build_seed_memberships
except ImportError:  # pragma: no cover - optional during partial installs
    CommitteeAggregate = None  # type: ignore[assignment]
    HawkDoveObservation = None  # type: ignore[assignment]
    OfficialAggregate = None  # type: ignore[assignment]
    OfficialsDirectory = None  # type: ignore[assignment]
    build_seed_memberships = None  # type: ignore[assignment]

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
        is_voting_member: bool = False,
        term_start: date | None = None,
        term_end: date | None = None,
        name_variants: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        speaker_key = self._speaker_key(name)
        existing = self._select_one("speakers", speaker_key=speaker_key)
        if existing:
            updates: Dict[str, Any] = {}
            if title and not existing.get("title"):
                updates["title"] = title
            if institution and not existing.get("institution"):
                updates["institution"] = institution
            if is_fomc_member and not existing.get("is_fomc_member"):
                updates["is_fomc_member"] = True
            if is_voting_member and not existing.get("is_voting_member"):
                updates["is_voting_member"] = True
            if term_start and not existing.get("term_start"):
                updates["term_start"] = term_start.isoformat()
            if term_end and not existing.get("term_end"):
                updates["term_end"] = term_end.isoformat()
            if name_variants:
                updates["name_variants"] = name_variants
            if updates:
                self.client.table("speakers").update(updates).eq("id", existing["id"]).execute()
            return existing["id"]

        result = self.client.table("speakers").insert(
            {
                "speaker_key": speaker_key,
                "name": name,
                "title": title,
                "institution": institution,
                "is_fomc_member": is_fomc_member,
                "is_voting_member": is_voting_member,
                "term_start": term_start.isoformat() if term_start else None,
                "term_end": term_end.isoformat() if term_end else None,
                "name_variants": name_variants or [],
                "metadata": metadata or {},
            }
        ).execute()
        return result.data[0]["id"]

    def upsert_speaker_membership(
        self,
        speaker_id: int,
        calendar_year: int,
        role: str,
        institution: str,
        is_fomc_participant: bool = True,
        is_voting_member: bool = False,
        effective_start: date | None = None,
        effective_end: date | None = None,
        notes: str | None = None,
    ) -> int:
        existing = (
            self.client.table("speaker_memberships")
            .select("*")
            .eq("speaker_id", speaker_id)
            .eq("calendar_year", calendar_year)
            .eq("role", role)
            .limit(1)
            .execute()
        )
        payload = {
            "speaker_id": speaker_id,
            "calendar_year": calendar_year,
            "role": role,
            "institution": institution,
            "is_fomc_participant": is_fomc_participant,
            "is_voting_member": is_voting_member,
            "effective_start": effective_start.isoformat() if effective_start else None,
            "effective_end": effective_end.isoformat() if effective_end else None,
            "notes": notes,
        }
        if existing.data:
            result = (
                self.client.table("speaker_memberships")
                .update(payload)
                .eq("id", existing.data[0]["id"])
                .execute()
            )
            return result.data[0]["id"]
        result = self.client.table("speaker_memberships").insert(payload).execute()
        return result.data[0]["id"]

    def seed_officials_directory(self) -> int:
        if build_seed_memberships is None:
            raise RuntimeError("hawk_dove.officials is not available")
        count = 0
        for record in build_seed_memberships():
            speaker_id = self.get_or_create_speaker(
                name=record.name,
                title=record.role,
                institution=record.institution,
                is_fomc_member=record.is_fomc_participant,
                is_voting_member=record.is_voting_member,
                term_start=record.term_start,
                term_end=record.term_end,
                name_variants=record.name_variants,
            )
            self.upsert_speaker_membership(
                speaker_id=speaker_id,
                calendar_year=record.calendar_year,
                role=record.role,
                institution=record.institution,
                is_fomc_participant=record.is_fomc_participant,
                is_voting_member=record.is_voting_member,
                effective_start=record.effective_start,
                effective_end=record.effective_end,
            )
            count += 1
        return count

    def get_membership_for_speaker(
        self,
        speaker_name: str,
        as_of: date,
    ) -> Optional[Dict[str, Any]]:
        speaker = self._select_one("speakers", speaker_key=self._speaker_key(speaker_name))
        if not speaker:
            # Fall back to name match.
            result = self.client.table("speakers").select("*").ilike("name", f"%{speaker_name}%").limit(1).execute()
            speaker = result.data[0] if result.data else None
        if not speaker:
            return None
        rows = (
            self.client.table("speaker_memberships")
            .select("*")
            .eq("speaker_id", speaker["id"])
            .eq("calendar_year", as_of.year)
            .execute()
        )
        for row in rows.data:
            start = date.fromisoformat(row["effective_start"]) if row.get("effective_start") else date(as_of.year, 1, 1)
            end = date.fromisoformat(row["effective_end"]) if row.get("effective_end") else date(as_of.year, 12, 31)
            if start <= as_of <= end:
                return {**row, "speaker": speaker}
        if rows.data:
            return {**rows.data[0], "speaker": speaker}
        return None

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

    # ---------------------------------------------------------------------
    # Hawk–dove scores (append-only)
    # ---------------------------------------------------------------------

    def insert_hawk_dove_score(
        self,
        observation: "HawkDoveObservation",
        document_id: int,
        analysis_run_id: int | None = None,
    ) -> int:
        if HawkDoveObservation is None:
            raise RuntimeError("hawk_dove.models is not available")

        # Never overwrite: identical score_key returns existing; otherwise always insert new version.
        existing = self._select_one("hawk_dove_scores", score_key=observation.score_key)
        if existing:
            return existing["id"]

        speaker_id = None
        if observation.speaker_name:
            speaker_id = self.get_or_create_speaker(
                observation.speaker_name,
                title=observation.role,
                institution=observation.institution,
                is_fomc_member=bool(observation.was_fomc_participant_as_of_date),
                is_voting_member=bool(observation.was_voter_as_of_date),
            )

        score = observation.score
        result = self.client.table("hawk_dove_scores").insert(
            {
                "score_key": observation.score_key,
                "document_id": document_id,
                "speaker_id": speaker_id,
                "speaker_name": observation.speaker_name,
                "speech_date": observation.speech_date.isoformat() if observation.speech_date else None,
                "document_type": observation.document_type,
                "source_url": observation.source_url,
                "source_hash": observation.source_hash,
                "overall_score": None if score.insufficient_policy_content else score.overall_score,
                "inflation_score": None if score.insufficient_policy_content else score.inflation_score,
                "labor_score": None if score.insufficient_policy_content else score.labor_score,
                "growth_score": None if score.insufficient_policy_content else score.growth_score,
                "policy_action_score": None if score.insufficient_policy_content else score.policy_action_score,
                "confidence": score.confidence,
                "rationale": score.rationale,
                "evidence": [item.model_dump() for item in score.evidence],
                "section_scores": [item.model_dump() for item in score.section_scores],
                "insufficient_policy_content": score.insufficient_policy_content,
                "was_voter_as_of_date": observation.was_voter_as_of_date,
                "was_fomc_participant_as_of_date": observation.was_fomc_participant_as_of_date,
                "prompt_version": observation.prompt_version,
                "model_version": observation.model_version,
                "model_parameters": observation.model_parameters,
                "extraction_version": observation.extraction_version,
                "calibration_version": observation.calibration_version,
                "analysis_run_id": analysis_run_id,
                "manual_override": observation.manual_override,
                "override_notes": observation.override_notes,
                "scored_at": observation.scored_at.isoformat(),
            }
        ).execute()
        return result.data[0]["id"]

    def get_hawk_dove_scores(
        self,
        speaker_name: str | None = None,
        limit: int = 100,
        include_insufficient: bool = False,
        model_version: str | None = None,
        prompt_version: str | None = None,
        calibration_version: str | None = None,
    ) -> List[Dict[str, Any]]:
        query = (
            self.client.table("hawk_dove_scores")
            .select("*")
            .order("speech_date", desc=True)
            .order("scored_at", desc=True)
            .limit(limit)
        )
        if speaker_name:
            query = query.eq("speaker_name", speaker_name)
        if model_version:
            query = query.eq("model_version", model_version)
        if prompt_version:
            query = query.eq("prompt_version", prompt_version)
        if calibration_version:
            query = query.eq("calibration_version", calibration_version)
        if not include_insufficient:
            query = query.eq("insufficient_policy_content", False)
        return query.execute().data

    def insert_official_score_snapshot(self, aggregate: "OfficialAggregate", snapshot_key: str | None = None) -> int:
        if OfficialAggregate is None:
            raise RuntimeError("hawk_dove.models is not available")
        from hawk_dove.snapshots import official_snapshot_key

        key = snapshot_key or official_snapshot_key(aggregate)
        existing = self._select_one("official_score_snapshots", snapshot_key=key)
        if existing:
            return existing["id"]
        speaker_id = None
        if aggregate.speaker_name:
            speaker_id = self.get_or_create_speaker(aggregate.speaker_name)
        result = self.client.table("official_score_snapshots").insert(
            {
                "snapshot_key": key,
                "speaker_id": speaker_id,
                "speaker_name": aggregate.speaker_name,
                "as_of_date": aggregate.as_of_date.isoformat(),
                "method": aggregate.method,
                "window_days": aggregate.window_days,
                "half_life_days": aggregate.half_life_days,
                "overall_score": aggregate.overall_score,
                "inflation_score": aggregate.inflation_score,
                "labor_score": aggregate.labor_score,
                "growth_score": aggregate.growth_score,
                "policy_action_score": aggregate.policy_action_score,
                "communication_count": aggregate.communication_count,
                "coverage_notes": aggregate.coverage_notes,
                "score_keys": aggregate.score_keys,
                "prompt_version": aggregate.prompt_version,
                "model_version": aggregate.model_version,
                "calibration_version": aggregate.calibration_version or "none",
            }
        ).execute()
        return result.data[0]["id"]

    def insert_committee_score_snapshot(self, aggregate: "CommitteeAggregate", snapshot_key: str | None = None) -> int:
        if CommitteeAggregate is None:
            raise RuntimeError("hawk_dove.models is not available")
        from hawk_dove.snapshots import committee_snapshot_key

        key = snapshot_key or committee_snapshot_key(aggregate)
        existing = self._select_one("committee_score_snapshots", snapshot_key=key)
        if existing:
            return existing["id"]
        result = self.client.table("committee_score_snapshots").insert(
            {
                "snapshot_key": key,
                "as_of_date": aggregate.as_of_date.isoformat(),
                "cohort": aggregate.cohort,
                "method": aggregate.method,
                "window_days": aggregate.window_days,
                "half_life_days": aggregate.half_life_days,
                "overall_score": aggregate.overall_score,
                "official_count": aggregate.official_count,
                "communication_count": aggregate.communication_count,
                "coverage_notes": aggregate.coverage_notes,
                "official_scores": [row.model_dump(mode="json") for row in aggregate.official_scores],
                "prompt_version": aggregate.prompt_version,
                "model_version": aggregate.model_version,
                "calibration_version": aggregate.calibration_version or "none",
            }
        ).execute()
        return result.data[0]["id"]

    def get_official_score_snapshots(
        self,
        speaker_name: str | None = None,
        model_version: str | None = None,
        method: str | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = (
            self.client.table("official_score_snapshots")
            .select("*")
            .order("as_of_date", desc=True)
            .limit(limit)
        )
        if speaker_name:
            query = query.eq("speaker_name", speaker_name)
        if model_version:
            query = query.eq("model_version", model_version)
        if method:
            query = query.eq("method", method)
        return query.execute().data

    def get_committee_score_snapshots(
        self,
        cohort: str | None = None,
        model_version: str | None = None,
        method: str | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = (
            self.client.table("committee_score_snapshots")
            .select("*")
            .order("as_of_date", desc=True)
            .limit(limit)
        )
        if cohort:
            query = query.eq("cohort", cohort)
        if model_version:
            query = query.eq("model_version", model_version)
        if method:
            query = query.eq("method", method)
        return query.execute().data

    # ---------------------------------------------------------------------
    # Calendar ingest runs (corpus-side; calendar project is read-only)
    # ---------------------------------------------------------------------

    def get_calendar_ingest_run(self, external_id: str) -> Optional[Dict[str, Any]]:
        return self._select_one("calendar_ingest_runs", external_id=external_id)

    def list_scored_calendar_external_ids(self, external_ids: Sequence[str]) -> set[str]:
        if not external_ids:
            return set()
        result = (
            self.client.table("calendar_ingest_runs")
            .select("external_id,status")
            .in_("external_id", list(external_ids))
            .execute()
        )
        return {
            row["external_id"]
            for row in (result.data or [])
            if row.get("status") == "scored"
        }

    def upsert_calendar_ingest_run(self, payload: Dict[str, Any]) -> int:
        external_id = payload["external_id"]
        existing = self.get_calendar_ingest_run(external_id)
        now = datetime.now(UTC).isoformat()
        row = {
            "external_id": external_id,
            "calendar_event_id": payload.get("calendar_event_id"),
            "speaker_name": payload.get("speaker_name"),
            "title": payload.get("title"),
            "scheduled_start": payload.get("scheduled_start"),
            "event_type": payload.get("event_type"),
            "source": payload.get("source"),
            "resolved_url": payload.get("resolved_url"),
            "status": payload.get("status", "pending"),
            "error": payload.get("error"),
            "document_key": payload.get("document_key"),
            "score_key": payload.get("score_key"),
            "model_version": payload.get("model_version"),
            "last_attempt_at": payload.get("last_attempt_at") or now,
            "scored_at": payload.get("scored_at"),
            "updated_at": now,
        }
        if existing:
            attempt_count = int(existing.get("attempt_count") or 0) + 1
            result = (
                self.client.table("calendar_ingest_runs")
                .update({**row, "attempt_count": attempt_count})
                .eq("id", existing["id"])
                .execute()
            )
            return result.data[0]["id"]
        result = self.client.table("calendar_ingest_runs").insert(
            {**row, "attempt_count": 1}
        ).execute()
        return result.data[0]["id"]


if __name__ == "__main__":
    db = Database()
    print("Database connection successful")
    recent = db.get_recent_documents_with_fingerprints(limit=5)
    print(f"Found {len(recent)} recent documents")
