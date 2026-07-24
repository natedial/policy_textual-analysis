# ADR: Hawk–Dove Scoring as a Parallel Product Layer

## Status

Accepted

## Context

The Fed Textual Change Tracker already normalizes Fed communications, extracts theme-level semantic fingerprints, and compares documents for shifts (orphaned concepts, stance/emphasis deltas, phrase anomalies). Its v1 architecture deliberately treats hawkish/dovish policy labels as internal-only and not the main output contract.

Separately, we want a passive research product that places each qualifying communication on a continuous **0–10 hawk–dove scale**, aggregates official and committee time series, and surfaces rankings with evidence. That product must not claim to reproduce any proprietary bank model.

## Decision

1. **Same monorepo, sibling package.** Implement hawk–dove scoring in `hawk_dove/`, consuming shared corpus code in `fed_tracker/` (normalization, document models) and shared persistence (`schema.sql`, `db.py`).
2. **Parallel artifacts, not a replacement.** Fingerprints and comparison results remain the textual-change product. Hawk–dove scores are a separate append-only artifact type. Neither product collapses into the other.
3. **Score the communication text.** The published 0–10 score is derived from normalized document text (and optional section synthesis for long docs). Theme fingerprints may exist for the same document but are non-authoritative for the published score.
4. **Never overwrite historical scores.** Rescoring creates a new row keyed by document + prompt/model/calibration versions. Aggregates and snapshots also version rather than mutate.
5. **MVP UI.** Use Streamlit for the first hawk–dove dashboard; keep the existing change-tracker Streamlit app as a separate debug surface.
6. **MVP sources.** Discovery collectors target at least two authoritative families: Federal Reserve Board speeches and New York Fed speeches.
7. **Swappable methodologies.** Document-level scorers implement `BaseHawkDoveScorer` and are selected via a registry (`heuristic`, `anthropic`, `roberta`). RoBERTa (`gtfintechlab/fomc-hawkish-dovish`) is an optional baseline for A/B comparison, not the default production path. Component scores from RoBERTa are keyword-routed over labeled sentences.
8. **Stored time series.** Official and committee EWMA aggregates are materialized into `official_score_snapshots` / `committee_score_snapshots`, branched by model versions. Observation rows remain the evidence source of truth.

## Consequences

- Schema gains hawk–dove score tables, official score snapshots, and time-aware voting membership.
- Agents and CLIs for textual change continue unchanged.
- Researchers can join fingerprints (“what shifted?”) with hawk–dove scores (“where is stance?”) on the same corpus.
- Editorial framing for hawk–dove outputs must label scores as independent model estimates, not facts, and not affiliated with Deutsche Bank or the Federal Reserve.
- Optional `requirements-roberta.txt` installs `transformers`/`torch` only when the RoBERTa method is needed.
