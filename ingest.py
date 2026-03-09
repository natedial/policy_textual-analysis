from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from db import Database
from fed_tracker.agent_service import FedTextAgentService
from fed_tracker.contract import cli_envelope
from fed_tracker.pipeline import AnalysisPipeline


def _load_metadata(raw: str | None) -> Dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze and persist Fed communication inputs.")
    parser.add_argument("url", nargs="?", help="Document URL to fetch and analyze")
    parser.add_argument("--urls-file", help="Path to a file containing one URL per line")
    parser.add_argument("--markdown-file", help="Path to a markdown/text file to analyze")
    parser.add_argument("--metadata-json", help="JSON metadata for markdown ingestion")
    parser.add_argument("--no-db", action="store_true", help="Run analysis without persisting to Supabase")
    args = parser.parse_args()

    metadata = _load_metadata(args.metadata_json)

    if args.no_db:
        pipeline = AnalysisPipeline(database=None)
        if args.markdown_file:
            markdown_text = Path(args.markdown_file).read_text()
            result = pipeline.analyze_markdown(markdown_text, metadata=metadata)
            payload = {
                "document": result.document.model_dump(mode="json"),
                "fingerprint": result.fingerprint.model_dump(mode="json"),
            }
        elif args.urls_file:
            urls = [line.strip() for line in Path(args.urls_file).read_text().splitlines() if line.strip()]
            payload = {
                "count": len(urls),
                "results": [
                    {
                        "document": bundle.document.model_dump(mode="json"),
                        "fingerprint": bundle.fingerprint.model_dump(mode="json"),
                    }
                    for bundle in (pipeline.analyze_url(url) for url in urls)
                ],
            }
        else:
            if not args.url:
                raise SystemExit("A URL, --urls-file, or --markdown-file is required")
            result = pipeline.analyze_url(args.url)
            payload = {
                "document": result.document.model_dump(mode="json"),
                "fingerprint": result.fingerprint.model_dump(mode="json"),
            }
    else:
        service = FedTextAgentService(database=Database())
        if args.markdown_file:
            payload = service.ingest_markdown_file(args.markdown_file, metadata=metadata)
        elif args.urls_file:
            urls = [line.strip() for line in Path(args.urls_file).read_text().splitlines() if line.strip()]
            payload = service.ingest_urls(urls)
        else:
            if not args.url:
                raise SystemExit("A URL, --urls-file, or --markdown-file is required")
            payload = service.ingest_url(args.url)

    print(json.dumps(cli_envelope(command="ingest", data=payload), indent=2))


if __name__ == "__main__":
    main()
