from __future__ import annotations

import argparse
import json

from db import Database
from fed_tracker.agent_service import FedTextAgentService
from fed_tracker.contract import cli_envelope
from fed_tracker.runner import load_manifest, load_urls_file, run_manifest, run_url_batch


def main() -> None:
    parser = argparse.ArgumentParser(description="Cron-target ingestion runner for Fed textual analysis.")
    parser.add_argument("--urls-file", help="Path to a newline-delimited URL file")
    parser.add_argument("--manifest", help="Path to a JSON manifest for URLs and markdown files")
    parser.add_argument("--no-skip-existing", action="store_true", help="Re-ingest URLs even if they already exist in storage")
    args = parser.parse_args()

    if not args.urls_file and not args.manifest:
        raise SystemExit("--urls-file or --manifest is required")

    service = FedTextAgentService(database=Database())

    if args.manifest:
        payload = run_manifest(service, load_manifest(args.manifest))
    else:
        payload = run_url_batch(
            service,
            load_urls_file(args.urls_file),
            skip_existing=not args.no_skip_existing,
        )

    print(json.dumps(cli_envelope(command="schedule_ingest", data=payload), indent=2))


if __name__ == "__main__":
    main()
