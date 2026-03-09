# Fed Textual Change Tracker

Agent-first semantic analysis for Federal Reserve communications.

The current codebase is oriented around a structured analysis pipeline rather than a UI-first workflow. The Streamlit app is a temporary debugging surface over the same pipeline that agents will use.

## What This Does

- Normalizes Fed communications from URLs today and markdown later
- Extracts a structured semantic fingerprint for each document
- Compares the newest document to a speaker's `t-1` document
- Scaffolds phrase-anomaly tracking across exact, normalized, and hashed forms
- Preserves replayable analysis artifacts for auditing and trust-building

## Current Direction

The repo now has a `fed_tracker/` package with five core layers:

- `normalization.py`: fetch and normalize HTML, PDF, or markdown into canonical documents
- `extraction.py`: semantic fingerprint extraction with Anthropic and a deterministic fallback
- `phrase_signals.py`: phrase rarity/anomaly scaffolding
- `comparison.py`: `t-1` and context-window comparison logic
- `pipeline.py`: orchestration layer for agent and UI callers

See [docs/V1_ARCHITECTURE.md](docs/V1_ARCHITECTURE.md) for the v1 design.
The current orchestrator-facing contract is documented in [API_CONTRACT.md](/Users/ndial/dev/textual_change_tracker/docs/API_CONTRACT.md).

## Current Source Coverage

Normalization is now source-aware rather than purely generic.

- specialized HTML extraction for `federalreserve.gov`
- specialized HTML extraction for `newyorkfed.org`
- source-configured extraction for:
  - `kansascityfed.org`
  - `clevelandfed.org`
  - `dallasfed.org`
  - `bostonfed.org`
  - `frbsf.org`
  - `minneapolisfed.org`
  - `stlouisfed.org`
  - `chicagofed.org`
  - `atlantafed.org`
  - `philadelphiafed.org`
  - `richmondfed.org`
- generic fallback extraction for anything not yet covered
- PDF extraction for linked speech and press-conference documents

The test suite now includes reduced local fixtures derived from live Federal Reserve Board speech pages, Board press-release pages, New York Fed speech pages, and Dallas Fed speech pages, so selector behavior is no longer validated only against synthetic HTML.

Boilerplate suppression is currently scaffolded for:

- `press_release`
- `statement`
- `press_conference`

That suppression layer is intentionally conservative and will expand as we build a stronger Fed-specific dictionary.

## Quick Start

### 1. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Set any values you need:

- `ANTHROPIC_API_KEY` for LLM-backed extraction
- `SUPABASE_URL` and `SUPABASE_KEY` for persistence

If `ANTHROPIC_API_KEY` is not set, the pipeline falls back to a deterministic heuristic extractor. That fallback is useful for testing structure, but not for production-quality semantic analysis.

### 4. Run the debug UI

```bash
streamlit run app.py
```

The UI compares a baseline URL with a newer URL and shows:

- normalized document metadata
- semantic fingerprints
- detected theme changes
- phrase anomalies
- the structured comparison artifact

If `SUPABASE_URL` and `SUPABASE_KEY` are set, the UI can also persist the target analysis and show stored `t-1`, `75d`, and `24m` comparison artifacts.

### 5. Run the ingestion entrypoint

With persistence enabled:

```bash
./venv/bin/python ingest.py "https://www.federalreserve.gov/newsevents/speech/powell20250129a.htm"
```

Without persistence:

```bash
./venv/bin/python ingest.py --no-db "https://www.federalreserve.gov/newsevents/speech/powell20250129a.htm"
```

Batch URL ingestion:

```bash
./venv/bin/python ingest.py --urls-file urls.txt
```

Markdown ingestion:

```bash
./venv/bin/python ingest.py --markdown-file speech.md --metadata-json '{"speaker_name":"Jerome H. Powell","speech_date":"2026-03-08","document_type":"speech"}'
```

The CLI prints the normalized document, fingerprint, and any stored comparison artifacts as JSON.

### 5a. Run the cron-target ingestion runner

For a newline-delimited URL file:

```bash
./venv/bin/python schedule_ingest.py --urls-file urls.txt
```

Example file: [urls.txt](/Users/ndial/dev/textual_change_tracker/examples/urls.txt)

For a JSON manifest:

```bash
./venv/bin/python schedule_ingest.py --manifest ingest_manifest.json
```

Example manifest: [ingest_manifest.json](/Users/ndial/dev/textual_change_tracker/examples/ingest_manifest.json)
Example markdown input: [sample_speech.md](/Users/ndial/dev/textual_change_tracker/examples/sample_speech.md)

### 6. Query stored artifacts

All CLI commands emit a stable versioned JSON envelope with:

- `api_version`
- `ok`
- `transport`
- `operation`
- `status_code`
- `data`

Timeline:

```bash
./venv/bin/python query_artifacts.py timeline "Jerome H. Powell" --limit 5
```

Recent comparisons:

```bash
./venv/bin/python query_artifacts.py comparisons "Jerome H. Powell" --type t_minus_1 --limit 5
```

Phrase anomalies:

```bash
./venv/bin/python query_artifacts.py phrases "Jerome H. Powell" --limit 10 --min-rarity 1.5
```

Latest stored document snapshot:

```bash
./venv/bin/python query_artifacts.py latest "Jerome H. Powell"
```

Orphaned concepts over 75 days:

```bash
./venv/bin/python query_artifacts.py orphaned "Jerome H. Powell" --window-days 75 --min-emphasis 3
```

Theme drift over 24 months:

```bash
./venv/bin/python query_artifacts.py drift "Jerome H. Powell" --theme INFLATION --window-days 730
```

Speaker brief:

```bash
./venv/bin/python query_artifacts.py brief "Jerome H. Powell" --theme INFLATION
```

Question-oriented brief:

```bash
./venv/bin/python query_artifacts.py question "Jerome H. Powell" "How has Powell's inflation rhetoric shifted over the last two years?"
```

### 7. Run the HTTP API

```bash
./venv/bin/python serve_api.py --host 127.0.0.1 --port 8000
```

The API is intended to stay on `127.0.0.1` for now. If you are reaching it over Tailscale, keep the listener local and expose it through your existing localhost workflow rather than binding it broadly.

Machine-readable schema:

- [openapi.json](/Users/ndial/dev/textual_change_tracker/docs/openapi.json)
- runtime endpoint: `GET /openapi.json`

Example calls:

```bash
curl "http://127.0.0.1:8000/speaker/brief?speaker_name=Jerome%20H.%20Powell&theme=INFLATION"
curl -X POST "http://127.0.0.1:8000/speaker/question" -H "Content-Type: application/json" -d '{"speaker_name":"Jerome H. Powell","question":"How has Powell\\'s inflation rhetoric shifted?"}'
curl -X POST "http://127.0.0.1:8000/ingest/urls" -H "Content-Type: application/json" -d '{"urls":["https://www.federalreserve.gov/newsevents/speech/jefferson20251107a.htm"],"skip_existing":true}'
```

## Database

The schema now supports:

- `source_documents`
- `documents`
- `document_segments`
- `analysis_runs`
- `fingerprints`
- `phrase_observations`
- `comparison_results`

Setup instructions are in [DATABASE_SETUP.md](DATABASE_SETUP.md).

## Python Agent Interface

For direct agent usage without shelling out through the CLI:

```python
from fed_tracker import FedTextAgentService

service = FedTextAgentService()
brief = service.speaker_brief("Jerome H. Powell", theme="INFLATION")
answer = service.answer_question(
    "Jerome H. Powell",
    "How has Powell's inflation rhetoric shifted over the last two years?",
)
```

The same service surface also supports automated ingestion:

```python
service.ingest_urls(["https://www.federalreserve.gov/newsevents/speech/jefferson20251107a.htm"])
```

## Tests

```bash
./venv/bin/python -m unittest discover -s tests
```

## Legacy Code

The `/poc` directory remains as a legacy reference implementation while the new pipeline is being built out. It is no longer the canonical architecture for the repo.
