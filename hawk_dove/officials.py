"""Time-aware Fed official membership and voting-status resolution."""

from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from hawk_dove.models import MembershipRecord


# Seed coverage for recent FOMC years used by the research prototype.
# Voting rotations for Reserve Bank presidents follow the published annual schedule.
_SEED_BOARD = [
    ("jerome_h_powell", "Jerome H. Powell", "Chair", "Board of Governors", True),
    ("philip_n_jefferson", "Philip N. Jefferson", "Vice Chair", "Board of Governors", True),
    ("michael_s_barr", "Michael S. Barr", "Vice Chair for Supervision", "Board of Governors", True),
    ("michelle_w_bowman", "Michelle W. Bowman", "Governor", "Board of Governors", True),
    ("lisa_d_cook", "Lisa D. Cook", "Governor", "Board of Governors", True),
    ("adriana_d_kugler", "Adriana D. Kugler", "Governor", "Board of Governors", True),
    ("christopher_j_waller", "Christopher J. Waller", "Governor", "Board of Governors", True),
]

# Reserve Bank presidents: (key, name, institution, voting years 2024-2026)
_SEED_PRESIDENTS = [
    ("john_c_williams", "John C. Williams", "New York Fed", {2024, 2025, 2026}),  # always votes
    ("susan_m_collins", "Susan M. Collins", "Boston Fed", {2024}),
    ("thomas_i_barkin", "Thomas I. Barkin", "Richmond Fed", {2024}),
    ("raphael_w_bostic", "Raphael W. Bostic", "Atlanta Fed", {2024}),
    ("mary_c_daly", "Mary C. Daly", "San Francisco Fed", {2024}),
    ("austan_d_goolsbee", "Austan D. Goolsbee", "Chicago Fed", {2025}),
    ("neel_kashkari", "Neel Kashkari", "Minneapolis Fed", {2026}),
    ("lorie_k_logan", "Lorie K. Logan", "Dallas Fed", {2025}),
    ("alberto_g_musalem", "Alberto G. Musalem", "St. Louis Fed", {2025}),
    ("jeffrey_r_schmid", "Jeffrey R. Schmid", "Kansas City Fed", {2026}),
    ("beth_m_hammack", "Beth M. Hammack", "Cleveland Fed", {2026}),
    ("patrick_t_harker", "Patrick T. Harker", "Philadelphia Fed", {2025}),
]


def build_seed_memberships(years: Iterable[int] | None = None) -> List[MembershipRecord]:
    years = list(years or [2024, 2025, 2026])
    records: List[MembershipRecord] = []

    for year in years:
        for key, name, role, institution, votes in _SEED_BOARD:
            records.append(
                MembershipRecord(
                    speaker_key=key,
                    name=name,
                    calendar_year=year,
                    role=role,
                    institution=institution,
                    is_fomc_participant=True,
                    is_voting_member=votes,
                    effective_start=date(year, 1, 1),
                    effective_end=date(year, 12, 31),
                    name_variants=_name_variants(name),
                )
            )
        for key, name, institution, voting_years in _SEED_PRESIDENTS:
            records.append(
                MembershipRecord(
                    speaker_key=key,
                    name=name,
                    calendar_year=year,
                    role="President",
                    institution=institution,
                    is_fomc_participant=True,
                    is_voting_member=year in voting_years,
                    effective_start=date(year, 1, 1),
                    effective_end=date(year, 12, 31),
                    name_variants=_name_variants(name),
                )
            )
    return records


def _name_variants(name: str) -> List[str]:
    parts = name.replace(".", "").split()
    variants = {name, name.replace(".", "")}
    if len(parts) >= 2:
        variants.add(f"{parts[0]} {parts[-1]}")
        variants.add(parts[-1])
        variants.add(f"{parts[0][0]}. {parts[-1]}")
    return sorted(variants)


class OfficialsDirectory:
    """In-memory directory for resolving voting status as-of a communication date."""

    def __init__(self, records: Optional[List[MembershipRecord]] = None):
        self.records = list(records or build_seed_memberships())
        self._by_name: Dict[str, List[MembershipRecord]] = {}
        for record in self.records:
            for variant in [record.name, *record.name_variants]:
                self._by_name.setdefault(variant.lower(), []).append(record)

    def resolve(
        self,
        speaker_name: Optional[str],
        as_of: Optional[date],
    ) -> Tuple[Optional[MembershipRecord], bool, bool]:
        if not speaker_name:
            return None, False, False
        candidates = self._by_name.get(speaker_name.lower(), [])
        if not candidates and " " in speaker_name:
            last = speaker_name.split()[-1].lower()
            candidates = [r for key, rows in self._by_name.items() if key.endswith(last) for r in rows]
        if not candidates:
            return None, False, False

        if as_of is None:
            record = candidates[-1]
            return record, record.is_voting_member, record.is_fomc_participant

        year_matches = [r for r in candidates if r.calendar_year == as_of.year]
        pool = year_matches or candidates
        for record in pool:
            start = record.effective_start or date(record.calendar_year, 1, 1)
            end = record.effective_end or date(record.calendar_year, 12, 31)
            if start <= as_of <= end:
                return record, record.is_voting_member, record.is_fomc_participant
        record = pool[-1]
        return record, record.is_voting_member, record.is_fomc_participant

    def is_voting_member(self, speaker_name: Optional[str], as_of: Optional[date]) -> bool:
        _, is_voter, _ = self.resolve(speaker_name, as_of)
        return is_voter

    def list_participants(self, as_of: date, voters_only: bool = False) -> List[MembershipRecord]:
        rows = [r for r in self.records if r.calendar_year == as_of.year]
        if voters_only:
            rows = [r for r in rows if r.is_voting_member]
        seen = set()
        unique: List[MembershipRecord] = []
        for row in rows:
            if row.speaker_key in seen:
                continue
            seen.add(row.speaker_key)
            unique.append(row)
        return unique
