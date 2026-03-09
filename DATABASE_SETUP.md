# Database Setup Guide

## Overview

The schema now targets an agent-first analysis workflow with replayable artifacts.

Core tables:
- `speakers`
- `source_documents`
- `documents`
- `document_segments`
- `analysis_runs`
- `fingerprints`
- `phrase_observations`
- `comparison_results`

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

## Next Build Targets

The pipeline can now persist via `fed_tracker.pipeline.AnalysisPipeline` and the `ingest.py` entrypoint.

## Next Build Targets

1. Add richer ingestion for pre-scraped markdown and site-specific scrapers
2. Add speaker-specific historical retrieval jobs for 75d/24m windows
3. Add agent-facing query tools over stored artifacts
4. Add stronger boilerplate suppression and phrase clustering
