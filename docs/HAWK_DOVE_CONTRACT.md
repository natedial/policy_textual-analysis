# Hawk–Dove Score Contract

## Document-level score JSON

Every qualifying communication produces this structured observation:

```json
{
  "overall_score": 6.8,
  "inflation_score": 7.5,
  "labor_score": 5.8,
  "growth_score": 5.4,
  "policy_action_score": 7.2,
  "confidence": 0.84,
  "rationale": "The official emphasized persistent inflation and supported maintaining restrictive policy.",
  "evidence": [
    {
      "quote": "Short source-grounded excerpt",
      "direction": "hawkish",
      "weight": 0.8,
      "start_char": 120,
      "end_char": 180
    }
  ],
  "insufficient_policy_content": false,
  "section_scores": []
}
```

### Field rules

| Field | Range / type | Notes |
|-------|--------------|-------|
| `overall_score` | 0.0–10.0 | 0 = extremely dovish, 5 = neutral, 10 = extremely hawkish |
| `inflation_score` | 0.0–10.0 | Inflation concern / restraint implied by inflation discussion |
| `labor_score` | 0.0–10.0 | Labor-market implications for policy restraint |
| `growth_score` | 0.0–10.0 | Growth / demand implications for policy restraint |
| `policy_action_score` | 0.0–10.0 | Explicit preference for hikes, holds, cuts, or restrictiveness |
| `confidence` | 0.0–1.0 | Model confidence in the observation |
| `rationale` | short string | One–three sentence explanation |
| `evidence` | list | Short traceable excerpts; required when overall &lt; 3.5 or &gt; 6.5 |
| `insufficient_policy_content` | bool | True when monetary-policy content is too limited to score |
| `section_scores` | list | Optional per-section scores for long documents |

Scores measure the **communication’s implied preference for restraint vs accommodation**, not the speaker’s reputation.

## Versioning metadata (always stored)

- `score_key` — unique observation id
- `document_key` / `source_hash`
- `prompt_version`
- `model_version`
- `model_parameters` (JSON)
- `extraction_version`
- `calibration_version` (nullable / `"none"` until calibration exists)
- `scored_at`
- `manual_override` (bool) + optional override notes

Rescoring never updates an existing row; it inserts a new version.

## Aggregation defaults

- Window: 90 days
- Weighting: exponential decay with 30-day half-life
- Committee averages: equal weight per official after computing each official’s window score
- Require ≥1 qualifying communication in the window
- Always report coverage counts alongside aggregates

## Observation → time-series contract

System of record is Supabase/Postgres (not CSV exports).

1. **Observations** (`hawk_dove_scores`): append-only per communication; never overwrite on rescore. Branch series by `prompt_version` / `model_version` / `calibration_version`.
2. **Official snapshots** (`official_score_snapshots`): materialized EWMA (default) points for each official as-of a calendar date, keyed by method + model versions so A/B series do not collide.
3. **Committee snapshots** (`committee_score_snapshots`): equal-weight rollups for `all_participants` and `voters` cohorts.
4. **Views**: `official_hawk_dove_timeseries`, `committee_hawk_dove_timeseries` for trend queries.
5. Materialize after `--persist` scoring or via `score_hawk_dove.py --materialize-from-db`.

CSV/JSON under `--output-dir` is export-only.

## Methodologies

Swappable via `hawk_dove.registry.get_scorer` / CLI `--method`:

| Method | `model_version` | Notes |
|--------|-----------------|-------|
| `heuristic` | `heuristic-hawkdove-v1` | Lexicon baseline |
| `anthropic` | Claude model id | Rubric LLM scorer |
| `roberta` | `gtfintechlab/fomc-hawkish-dovish` | Sentence classifier baseline; component scores are keyword-routed, not native heads |

Use `--compare-methods heuristic,roberta` for side-by-side export.

## Editorial labels

All user-facing surfaces must disclose that scores are independent model estimates for research, not investment advice, and are unaffiliated with Deutsche Bank or the Federal Reserve.
