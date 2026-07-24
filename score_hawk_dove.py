#!/usr/bin/env python3
"""CLI for hawk–dove research scoring, A/B compare, and snapshot materialization."""

from __future__ import annotations

import argparse
import json
import os
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
from hawk_dove.pipeline import HawkDovePipeline
from hawk_dove.registry import KNOWN_METHODS, get_scorer
from hawk_dove.snapshots import materialize_snapshots, observations_from_score_rows


def _load_metadata(raw: str | None) -> Dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


def _parse_methods(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _score_inputs(
    pipeline: HawkDovePipeline,
    *,
    url: str | None,
    urls_file: str | None,
    markdown_file: str | None,
    metadata: Dict[str, Any],
    persist: bool,
) -> List[Any]:
    scored = []
    if markdown_file:
        markdown_text = Path(markdown_file).read_text()
        scored.append(pipeline.score_markdown(markdown_text, metadata=metadata, persist=persist))
    elif urls_file:
        urls = [
            line.strip()
            for line in Path(urls_file).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        scored.extend(pipeline.score_urls(urls, persist=persist))
    elif url:
        scored.append(pipeline.score_url(url, persist=persist))
    return scored


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score Fed communications on a 0–10 hawk–dove scale (independent research estimates)."
    )
    parser.add_argument("url", nargs="?", help="Document URL to fetch and score")
    parser.add_argument("--urls-file", help="Path to a file containing one URL per line")
    parser.add_argument("--markdown-file", help="Path to a markdown/text file to score")
    parser.add_argument("--metadata-json", help="JSON metadata for markdown scoring")
    parser.add_argument(
        "--method",
        default="default",
        help=f"Scoring method: default|{'|'.join(KNOWN_METHODS)}",
    )
    parser.add_argument(
        "--heuristic",
        action="store_true",
        help="Deprecated alias for --method heuristic",
    )
    parser.add_argument(
        "--compare-methods",
        help="Comma-separated methods to score side-by-side (e.g. heuristic,roberta)",
    )
    parser.add_argument("--persist", action="store_true", help="Persist scores/snapshots to Supabase when configured")
    parser.add_argument("--output-dir", help="Write CSV/JSON observation bundle to this directory")
    parser.add_argument("--as-of", help="Aggregation as-of date (YYYY-MM-DD); default today")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--half-life-days", type=float, default=DEFAULT_HALF_LIFE_DAYS)
    parser.add_argument(
        "--materialize-from-db",
        action="store_true",
        help="Materialize official/committee snapshots from persisted hawk_dove_scores",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discover new speech URLs from Board + NY Fed indexes",
    )
    parser.add_argument(
        "--discover-families",
        default="board,nyfed",
        help="Comma-separated source families for --discover (default: board,nyfed)",
    )
    args = parser.parse_args()

    method = "heuristic" if args.heuristic else args.method
    compare_methods = _parse_methods(args.compare_methods)
    officials = OfficialsDirectory()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    metadata = _load_metadata(args.metadata_json)

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

    database = None
    if args.persist or args.materialize_from_db:
        if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
            from db import Database

            database = Database()
        elif args.persist or args.materialize_from_db:
            raise SystemExit("Persistence requires SUPABASE_URL and SUPABASE_KEY")

    if args.materialize_from_db:
        assert database is not None
        model_version = None if method == "default" else get_scorer(method).model_version
        rows = database.get_hawk_dove_scores(limit=500, model_version=model_version)
        observations = observations_from_score_rows(rows)
        batch = materialize_snapshots(
            observations,
            as_of_date=as_of,
            database=database,
            window_days=args.window_days,
            half_life_days=args.half_life_days,
            officials=officials,
            model_version=model_version,
        )
        payload["materialized"] = {
            "as_of_date": as_of.isoformat(),
            "observation_count": len(observations),
            "model_version": model_version,
            "official_snapshot_ids": batch.persisted_official_ids,
            "committee_snapshot_ids": batch.persisted_committee_ids,
            "committee_average": batch.committee_all.model_dump(mode="json") if batch.committee_all else None,
            "voting_member_average": (
                batch.committee_voters.model_dump(mode="json") if batch.committee_voters else None
            ),
        }
        print(json.dumps(cli_envelope(command="score_hawk_dove", data=payload), indent=2))
        return

    has_inputs = bool(args.markdown_file or args.urls_file or args.url)
    if not has_inputs and not args.discover:
        raise SystemExit("A URL, --urls-file, --markdown-file, --discover, or --materialize-from-db is required")

    methods_to_run = compare_methods or ([method] if has_inputs else [])
    comparisons: Dict[str, List[Any]] = {}
    primary_observations: List[Any] = []

    for method_name in methods_to_run:
        scorer = get_scorer(None if method_name == "default" else method_name)
        pipeline = HawkDovePipeline(scorer=scorer, officials=officials, database=database)
        scored = _score_inputs(
            pipeline,
            url=args.url,
            urls_file=args.urls_file,
            markdown_file=args.markdown_file,
            metadata=metadata,
            persist=bool(args.persist and database is not None),
        )
        observations = [item.observation for item in scored]
        comparisons[method_name] = observations
        if not primary_observations:
            primary_observations = observations
        if args.persist and observations and database is not None:
            materialize_snapshots(
                observations,
                as_of_date=as_of,
                database=database,
                window_days=args.window_days,
                half_life_days=args.half_life_days,
                officials=officials,
                model_version=observations[0].model_version,
            )

    observations = primary_observations
    if observations:
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
        payload["method"] = methods_to_run[0] if methods_to_run else method
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
        if compare_methods:
            payload["comparisons"] = {
                name: [obs.model_dump(mode="json") for obs in obs_list]
                for name, obs_list in comparisons.items()
            }
        if args.output_dir:
            paths = write_bundle(
                observations,
                args.output_dir,
                officials=ranks,
                committee=committee,
                comparisons=comparisons if compare_methods else None,
            )
            payload["exports"] = paths
        if args.persist:
            payload["persisted"] = {
                "as_of_date": as_of.isoformat(),
                "methods": list(comparisons.keys()),
            }

    print(json.dumps(cli_envelope(command="score_hawk_dove", data=payload), indent=2))


if __name__ == "__main__":
    main()
