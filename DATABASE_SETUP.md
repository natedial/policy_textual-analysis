# Database Setup Guide

## Overview

The schema now targets an agent-first analysis workflow with replayable artifacts.

Core tables:
- `speakers` (includes term dates, name variants, voting flags)
- `speaker_memberships` (time-aware FOMC participation / voting by year)
- `source_documents`
- `documents`
- `document_segments`
- `analysis_runs`
- `fingerprints`
- `phrase_observations`
- `comparison_results`
- `hawk_dove_scores` (append-only hawk–dove observations)
- `official_score_snapshots`
- `committee_score_snapshots`

For existing deployments, apply [migrations/001_hawk_dove_layer.sql](migrations/001_hawk_dove_layer.sql) after the base schema, then [migrations/002_calendar_ingest_runs.sql](migrations/002_calendar_ingest_runs.sql) for schedule-driven ingest status.

### Calendar project (separate Supabase)

Schedule polling reads `public.speaker_events` from a different Supabase project using:

```bash
CALENDAR_SUPABASE_URL=https://your-calendar-project.supabase.co
CALENDAR_SUPABASE_KEY=your-calendar-read-key
```

Ingest status is written only to the corpus `calendar_ingest_runs` table — the poller does not update calendar `speech_id` / `status`.

## Supabase Setup

### 1. Create a project

1. Go to https://supabase.com
2. Create a new project
3. Save the project URL and API key

### 2. Apply the schema

1. Open the SQL editor in Supabase
2. Paste the contents of `schema.sql`
3. Run the script

### 3. Configure `.env`

```bash
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-anon-key
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.your-project-ref.supabase.co:5432/postgres
```

### 4. Verify access

```bash
./venv/bin/python -c "from db import Database; db = Database(); print(len(db.get_recent_documents_with_fingerprints(limit=5)))"
```

## Schema Notes

### `source_documents`
Stores the fetched or scraped source payload before normalization.

### `documents`
Stores the normalized canonical document used for analysis.

### `document_segments`
Stores optional paragraph or speaker-turn segmentation for transcript-like content.

### `analysis_runs`
Stores replay metadata for extraction and comparison steps.

### `fingerprints`
Stores structured semantic fingerprints for a normalized document.

### `phrase_observations`
Stores exact, normalized, and hashed phrase-level anomaly records.

### `comparison_results`
Stores structured comparison artifacts across `t-1` and context windows.

### `speaker_memberships`
Stores calendar-year FOMC participation and voting status used to resolve voter flags as-of each communication date.

### `hawk_dove_scores`
Append-only hawk–dove score observations. Rescoring inserts a new version; historical rows are never overwritten.

### Official / committee snapshots
Versioned aggregate tables for research dashboards and meeting-cycle comparisons.

Seed memberships with:

```bash
python seed_officials.py
```

## Next Build Targets

The pipeline can now persist via `fed_tracker.pipeline.AnalysisPipeline` and the `ingest.py` entrypoint.

1. Add richer listing-page collectors beyond Board + NY Fed discovery
2. Add speaker-specific historical retrieval jobs for 75d/24m windows
3. Expand human-reviewed hawk–dove calibration datasets
4. Add stronger boilerplate suppression and phrase clustering
