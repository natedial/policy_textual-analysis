#!/usr/bin/env python3
"""Seed time-aware officials / voting membership into Supabase."""

from __future__ import annotations

import json

from db import Database
from hawk_dove.officials import build_seed_memberships


def main() -> None:
    db = Database()
    count = db.seed_officials_directory()
    sample = [
        {
            "name": record.name,
            "year": record.calendar_year,
            "institution": record.institution,
            "voting": record.is_voting_member,
        }
        for record in build_seed_memberships([2025])[:5]
    ]
    print(json.dumps({"seeded_membership_rows": count, "sample_2025": sample}, indent=2))


if __name__ == "__main__":
    main()
