from __future__ import annotations

import argparse
import json

from fed_tracker.contract import cli_envelope
from fed_tracker.query import QueryService


def main() -> None:
    parser = argparse.ArgumentParser(description="Query stored Fed textual analysis artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    timeline = subparsers.add_parser("timeline")
    timeline.add_argument("speaker_name")
    timeline.add_argument("--limit", type=int, default=10)

    comparisons = subparsers.add_parser("comparisons")
    comparisons.add_argument("speaker_name")
    comparisons.add_argument("--type", dest="comparison_type")
    comparisons.add_argument("--limit", type=int, default=10)

    phrases = subparsers.add_parser("phrases")
    phrases.add_argument("speaker_name")
    phrases.add_argument("--limit", type=int, default=20)
    phrases.add_argument("--min-rarity", type=float, default=None)

    orphaned = subparsers.add_parser("orphaned")
    orphaned.add_argument("speaker_name")
    orphaned.add_argument("--window-days", type=int, default=75)
    orphaned.add_argument("--min-emphasis", type=int, default=3)

    drift = subparsers.add_parser("drift")
    drift.add_argument("speaker_name")
    drift.add_argument("--theme")
    drift.add_argument("--window-days", type=int, default=730)
    drift.add_argument("--limit", type=int, default=20)

    brief = subparsers.add_parser("brief")
    brief.add_argument("speaker_name")
    brief.add_argument("--theme")

    question = subparsers.add_parser("question")
    question.add_argument("speaker_name")
    question.add_argument("question")

    latest = subparsers.add_parser("latest")
    latest.add_argument("speaker_name")

    args = parser.parse_args()
    service = QueryService()

    if args.command == "timeline":
        payload = service.speaker_timeline(args.speaker_name, limit=args.limit)
    elif args.command == "comparisons":
        payload = service.recent_comparisons(
            args.speaker_name,
            comparison_type=args.comparison_type,
            limit=args.limit,
        )
    elif args.command == "phrases":
        payload = service.phrase_anomalies(
            args.speaker_name,
            limit=args.limit,
            min_rarity=args.min_rarity,
        )
    elif args.command == "orphaned":
        payload = service.orphaned_concepts(
            args.speaker_name,
            window_days=args.window_days,
            min_emphasis=args.min_emphasis,
        )
    elif args.command == "drift":
        payload = service.theme_drift(
            args.speaker_name,
            theme=args.theme,
            window_days=args.window_days,
            limit=args.limit,
        )
    elif args.command == "brief":
        payload = service.speaker_brief(
            args.speaker_name,
            theme=args.theme,
        )
    elif args.command == "question":
        payload = service.answer_speaker_question(
            args.speaker_name,
            args.question,
        )
    else:
        payload = service.latest_document_snapshot(args.speaker_name)

    print(json.dumps(cli_envelope(command=f"query:{args.command}", data=payload), indent=2))


if __name__ == "__main__":
    main()
