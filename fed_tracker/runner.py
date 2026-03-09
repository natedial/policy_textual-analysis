from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fed_tracker.agent_service import FedTextAgentService


def load_urls_file(path: str) -> List[str]:
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip() and not line.strip().startswith("#")]


def load_manifest(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text())


def run_url_batch(
    service: FedTextAgentService,
    urls: Iterable[str],
    skip_existing: bool = True,
) -> Dict[str, Any]:
    return service.ingest_urls(urls, skip_existing=skip_existing)


def run_manifest(
    service: FedTextAgentService,
    manifest: Dict[str, Any],
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []

    url_payload = manifest.get("urls") or []
    if url_payload:
        results.append(
            {
                "type": "urls",
                "result": service.ingest_urls(url_payload, skip_existing=manifest.get("skip_existing", True)),
            }
        )

    for markdown_item in manifest.get("markdown_files", []):
        path = markdown_item["path"]
        metadata = markdown_item.get("metadata") or {}
        results.append(
            {
                "type": "markdown_file",
                "path": path,
                "result": service.ingest_markdown_file(path, metadata=metadata),
            }
        )

    return {
        "count": len(results),
        "results": results,
    }
