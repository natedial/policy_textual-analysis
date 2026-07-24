#!/usr/bin/env python3
"""CLI for hawk–dove research scoring and export."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from fed_tracker.contract import cli_envelope
from hawk_dove.aggregation import (
    DEFAULT_HALF_LIFE_DAYS,
    DEFAULT_WINDOW_DAYS,
    aggregate_committee,
    ranked_officials,
)
from hawk_dove.discovery import discover_new_urls
from hawk_dove.export import write_bundle
from hawk_dove.officials import OfficialsDirectory
from hawk_dove.pipeline import HawkDovePipeline, build_pipeline
from hawk_dove.scoring import HeuristicHawkDoveScorer


def _load_metadata(raw: str | None) -> Dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score Fed communications on a 0–10 hawk–dove scale (independent research estimates)."
    )
    parser.add_argument("url", nargs="?", help="Document URL to fetch and score")
    parser.add_argument("--urls-file", help="Path to a file containing one URL per line")
    parser.add_argument("--markdown-file", help="Path to a markdown/text file to score")
    parser.add_argument("--metadata-json", help="JSON metadata for markdown scoring")
    parser.add_argument("--heuristic", action="store_true", help="Force heuristic scorer")
    parser.add_argument("--persist", action="store_true", help="Persist scores to Supabase when configured")
    parser.add_argument("--output-dir", help="Write CSV/JSON observation bundle to this directory")
    parser.add_argument("--as-of", help="Aggregation as-of date (YYYY-MM-DD); default today")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--half-life-days", type=float, default=DEFAULT_HALF_LIFE_DAYS)
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discover new speech URLs from Board + NY Fed indexes (no scoring unless combined with scoring inputs)",
    )
    parser.add_argument(
        "--discover-families",
        default="board,nyfed",
        help="Comma-separated source families for --discover (default: board,nyfed)",
    )
    args = parser.parse_args()

    officials = OfficialsDirectory()
    if args.heuristic:
        pipeline = HawkDovePipeline(scorer=HeuristicHawkDoveScorer(), officials=officials)
    else:
        pipeline = build_pipeline(persist=args.persist)
        pipeline.officials = officials

    payload: Dict[str, Any] = {
        "disclaimer": (
            "Scores are independent model estimates for research purposes only. "
            "Not affiliated with Deutsche Bank or the Federal Reserve. Not investment advice."
        )
    }

    if args.discover:
        families = [item.strip() for item in args.discover_families.split(",") if item.strip()]
        discovered = discover_new_urls(source_families=families)
        payload["discovered"] = [
            {
                "url": item.url,
                "source_family": item.source_family,
                "title": item.title,
                "date_hint": item.date_hint.isoformat() if item.date_hint else None,
            }
            for item in discovered
        ]

    scored = []
    metadata = _load_metadata(args.metadata_json)
    if args.markdown_file:
        markdown_text = Path(args.markdown_file).read_text()
        scored.append(pipeline.score_markdown(markdown_text, metadata=metadata, persist=args.persist))
    elif args.urls_file:
        urls = [
            line.strip()
            for line in Path(args.urls_file).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        scored.extend(pipeline.score_urls(urls, persist=args.persist))
    elif args.url:
        scored.append(pipeline.score_url(args.url, persist=args.persist))
    elif not args.discover:
        raise SystemExit("A URL, --urls-file, --markdown-file, or --discover is required")

    observations = [item.observation for item in scored]
    if observations:
        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
        ranks = ranked_officials(
            observations,
            as_of_date=as_of,
            window_days=args.window_days,
            half_life_days=args.half_life_days,
            officials=officials,
        )
        committee = aggregate_committee(
            observations,
            as_of_date=as_of,
            cohort="all_participants",
            window_days=args.window_days,
            half_life_days=args.half_life_days,
            officials=officials,
        )
        voters = aggregate_committee(
            observations,
            as_of_date=as_of,
            cohort="voters",
            window_days=args.window_days,
            half_life_days=args.half_life_days,
            officials=officials,
        )
        payload["observations"] = [obs.model_dump(mode="json") for obs in observations]
        payload["official_ranks"] = [row.model_dump(mode="json") for row in ranks]
        payload["committee_average"] = committee.model_dump(mode="json")
        payload["voting_member_average"] = voters.model_dump(mode="json")
        payload["coverage"] = {
            "observation_count": len(observations),
            "insufficient_policy_content_count": sum(
                1 for obs in observations if obs.score.insufficient_policy_content
            ),
            "committee_officials_with_scores": committee.official_count,
            "voter_officials_with_scores": voters.official_count,
        }
        if args.output_dir:
            paths = write_bundle(
                observations,
                args.output_dir,
                officials=ranks,
                committee=committee,
            )
            payload["exports"] = paths

    print(json.dumps(cli_envelope(command="score_hawk_dove", data=payload), indent=2))


if __name__ == "__main__":
    main()
