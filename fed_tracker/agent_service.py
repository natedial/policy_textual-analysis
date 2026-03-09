from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from db import Database
from fed_tracker.pipeline import AnalysisPipeline, StoredAnalysisResult
from fed_tracker.query import QueryService


class FedTextAgentService:
    def __init__(self, database: Optional[Database] = None):
        self.database = database or Database()
        self.pipeline = AnalysisPipeline(database=self.database)
        self.query = QueryService(database=self.database)

    def ingest_url(self, url: str) -> Dict[str, Any]:
        result = self.pipeline.analyze_and_store_url(url)
        return self._stored_result_payload(result)

    def ingest_url_if_new(self, url: str) -> Dict[str, Any]:
        if self.database.source_document_exists(url):
            return {
                "url": url,
                "skipped": True,
                "reason": "already_ingested",
            }
        payload = self.ingest_url(url)
        payload["url"] = url
        payload["skipped"] = False
        return payload

    def ingest_urls(self, urls: Iterable[str], skip_existing: bool = True) -> Dict[str, Any]:
        results = []
        for url in urls:
            if not url.strip():
                continue
            clean_url = url.strip()
            if skip_existing:
                results.append(self.ingest_url_if_new(clean_url))
            else:
                payload = self.ingest_url(clean_url)
                payload["url"] = clean_url
                payload["skipped"] = False
                results.append(payload)
        return {
            "count": len(results),
            "ingested": sum(1 for item in results if not item.get("skipped")),
            "skipped": sum(1 for item in results if item.get("skipped")),
            "results": results,
        }

    def ingest_markdown(self, markdown_text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result = self.pipeline.analyze_and_store_markdown(markdown_text, metadata=metadata)
        return self._stored_result_payload(result)

    def ingest_markdown_file(self, path: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        markdown_text = Path(path).read_text()
        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("source_type", "markdown_file")
        merged_metadata.setdefault("source_path", path)
        return self.ingest_markdown(markdown_text, metadata=merged_metadata)

    def speaker_brief(self, speaker_name: str, theme: Optional[str] = None) -> Dict[str, Any]:
        return self.query.speaker_brief(speaker_name, theme=theme)

    def answer_question(self, speaker_name: str, question: str) -> Dict[str, Any]:
        return self.query.answer_speaker_question(speaker_name, question)

    def recent_comparisons(self, speaker_name: str, comparison_type: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        return self.query.recent_comparisons(speaker_name, comparison_type=comparison_type, limit=limit)

    def speaker_timeline(self, speaker_name: str, limit: int = 10) -> Dict[str, Any]:
        return self.query.speaker_timeline(speaker_name, limit=limit)

    def _stored_result_payload(self, result: StoredAnalysisResult) -> Dict[str, Any]:
        return {
            "document": result.bundle.document.model_dump(mode="json"),
            "fingerprint": result.bundle.fingerprint.model_dump(mode="json"),
            "persisted": result.persisted.__dict__ if result.persisted else None,
            "comparisons": {key: value.model_dump(mode="json") for key, value in result.comparisons.items()},
            "context_summaries": result.context_summaries,
        }
