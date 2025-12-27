# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Textual Change Tracker** is a system for analyzing shifts in Federal Reserve communications over time. It tracks sentiment, emphasis, and verbiage changes in speeches, press statements, and transcripts from Fed officials to identify policy signals.

### Core Use Cases
1. Track sentiment and emphasis shifts by individual Fed policymakers
2. Detect deliberate textual modifications in FOMC press statements
3. Identify "orphaned concepts" (themes dropped from recent communications)
4. Distinguish between boilerplate repetition and intentional signaling

## Architecture

### System Components

**1. Ingestion Pipeline (Continuous Processing)**
- Web scraper with cron-style triggers for automated monitoring
- Targets: Federal Reserve Board + 11 Regional Fed Banks
- Detects and ingests new speeches, statements, and interview transcripts
- Polling interval or push notification triggers

**2. Analysis Engine ("The Brain")**
- **Methodology**: Recursive textual criticism approach
  - **Word Level**: Etymology, speaker-specific historical usage, frequency analysis
  - **Sentence Level**: Syntactic context, voice pattern shifts (active/passive)
  - **Paragraph/Whole Level**: Thematic emphasis, structural hierarchy
- **Categorization**: Automated tagging (e.g., "Hawkish Drift", "New Risk Factor", "Softening on Inflation")
- **Signal Detection**: Differentiates boilerplate from intentional changes
- **Omission Analysis**: Detects "orphaned concepts" absent from current speech but present in previous $N$ speeches
- **Note**: Exogenous factors (economic data, fiscal policy) are out of scope for Phase 1

**3. Data Layer (Supabase/PostgreSQL)**

Core tables structure:
- `Speeches`: Raw text, speaker metadata, date, type (speech/statement/interview)
- `Semantics`: Vector embeddings, sentiment scores, key phrase extraction
- `Detected_Shifts`: Delta between current and historical entries
- `Analysis_Log`: Automated categorization decisions

**Future-proofing**: Architecture supports `Historical_Corpus` table for baseline vector store. Query logic should reference this table even if unpopulated initially (moving window approach for Phase 1).

**4. User Interaction**

- **Layer 1 - "Push" (Real-time Alerts)**
  - Background worker monitoring `Detected_Shifts` table
  - Email/notification synthesis for detected shifts

- **Layer 2 - "Pull" (Ad-hoc Analysis)**
  - Chat agent with Streamlit split-pane UI
  - Renders side-by-side textual comparisons with shift annotations

## Data Sources

Federal Reserve speech repositories (11 Regional Banks + Board of Governors):
- Board of Governors: https://www.federalreserve.gov/newsevents/speeches.htm
- New York Fed: https://www.newyorkfed.org/newsevents/speeches/
- Kansas City Fed: https://www.kansascityfed.org/speeches/
- Cleveland Fed: https://www.clevelandfed.org/collections/speeches
- Dallas Fed: https://www.dallasfed.org/news/speeches
- Boston Fed: https://www.bostonfed.org/news-and-events/speeches.aspx
- San Francisco Fed: https://www.frbsf.org/news-and-media/speeches/
- Minneapolis Fed: https://www.minneapolisfed.org/publications-archive/all-speeches
- St. Louis Fed: https://www.stlouisfed.org/from-the-president/remarks
- Chicago Fed: https://www.chicagofed.org/publications/speeches/speech-archive
- Atlanta Fed: https://www.atlantafed.org/news/speeches
- Philadelphia Fed: https://www.philadelphiafed.org/the-economy/monetary-policy
- Richmond Fed: https://www.richmondfed.org/press_room/speeches

## Development Notes

### Technology Stack
- **Database**: Supabase/PostgreSQL with pgvector for embeddings
- **UI**: Streamlit (split-pane interface for comparative analysis)
- **Web Scraping**: TBD (BeautifulSoup/Scrapy/Playwright)
- **Embeddings**: TBD (OpenAI/local models)
- **Sentiment Analysis**: TBD

### Key Design Principles
- **Day 1 Requirement**: Omission analysis must be functional from launch
- **Phased Approach**: System operates on moving window initially; historical baseline ingestion is Phase 2
- **External Storage**: PostgreSQL required for relational complexity and volume
- **Signal over Noise**: Focus on detecting intentional changes, filtering boilerplate

### Architecture Considerations
- Build query logic for `Historical_Corpus` even if table remains unpopulated in Phase 1
- Orphaned concept detection requires tracking themes across previous $N$ speeches
- Shift detection must account for speaker-specific historical patterns

## Current Implementation

### Proof of Concept (PoC)

Located in `/poc` directory. Validates the semantic extraction approach.

**Core Approach**: Extract structured semantic representations from speeches, then compare those structures rather than doing text diffs.

**Key Components**:
- `extract.py`: Semantic fingerprint extraction using Claude API
  - Extracts themes (INFLATION, LABOR_MARKETS, HOUSING, etc.)
  - For each theme: stance, trajectory, emphasis score, hedging level, key passages
  - Pydantic models for type safety
- `compare.py`: Shift detection engine
  - Compares semantic fingerprints across speeches
  - Detects: stance shifts, emphasis changes, orphaned concepts, new themes
  - Categorizes shifts: HAWKISH_DRIFT, DOVISH_PIVOT, NEW_EMPHASIS, ORPHANED_CONCEPT, etc.
  - Assigns significance: HIGH, MEDIUM, LOW
- `validate.py`: Evidence verification
  - Verifies quotes exist in source texts
  - Negative control test (compare speech to itself)
- `run_poc.py`: Orchestrator
  - Runs full validation pipeline
  - Generates HTML report with results

**Running the PoC**:
```bash
export ANTHROPIC_API_KEY=your_key
cd poc
python run_poc.py
```

**Validation Approach**:
1. **Extraction Consistency**: Extract fingerprint from same speech twice - should be >90% consistent
2. **Evidence Verification**: All quoted passages must exist in source text
3. **Negative Control**: Comparing speech to itself should yield zero significant shifts
4. **Shift Detection**: Identify stance changes, emphasis shifts, orphaned concepts

**Success Criteria**:
- Extraction consistency ≥90%
- Evidence verification 100%
- Zero spurious shifts in negative control
- Catches meaningful shifts missed by word-level diff tools

### Technology Stack (PoC)
- **LLM**: Claude Sonnet 4.5 via Anthropic API
- **Prompts**: `/prompts/extraction_prompt.txt` - structured theme extraction
- **Models**: Pydantic for type-safe semantic fingerprints
- **Scraping**: BeautifulSoup for Fed speech pages
- **Output**: HTML validation reports

## Database Integration

### Schema (`schema.sql`)

PostgreSQL/Supabase schema with 4 core tables:
- **speakers**: Fed officials (name, title, institution)
- **speeches**: Raw content (URL, speaker, date, full text)
- **fingerprints**: Extracted semantic data (themes JSON, policy implications)
- **detected_shifts**: Comparison results (shifts JSON, significance counts)

**Key features**:
- JSONB columns for flexible theme storage
- GIN indexes for fast JSON queries
- Views for common queries (recent_speeches_with_fingerprints, high_significance_shifts)
- Seed data for current Board members

### Database Client (`db.py`)

Python wrapper around Supabase API:
- `insert_speech()` - Add new speech to database
- `insert_fingerprint()` - Store semantic extraction
- `insert_detected_shifts()` - Save comparison results
- `get_speaker_timeline()` - Retrieve all speeches for a speaker
- `speech_exists()` - Check for duplicates before scraping

**Setup**: See `DATABASE_SETUP.md` for Supabase configuration instructions.

### Next Steps
1. Build ingestion CLI (`ingest.py`) to add speeches to database
2. Modify PoC to save results to DB instead of HTML
3. Implement N-speech historical tracking for orphan detection
4. Build Streamlit UI for interactive exploration
5. Automated scraping pipeline
