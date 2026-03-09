# V1 Architecture

## Product Goal

Build an agent-first textual intelligence system for Federal Reserve communications.
The system should support both:

- fast reaction analysis on a newly published statement, speech, testimony, or interview
- slower longitudinal analysis of a policymaker's rhetorical and thematic evolution over time

The Streamlit UI is a temporary debugging and inspection surface. The primary interface is structured data that agents can query and compose.

## Design Decisions

### Core product behaviors

- Default comparison: newest document vs the prior same-speaker document (`t-1`)
- Context windows:
  - trailing `75d` for orphaned concepts and near-term context
  - trailing `24m` for longer-run speaker baseline
- Scope: any public Fed policymaker communication
- Error preference: tolerate some false positives rather than miss meaningful shifts
- Evidence standard: preserve source quotes and replay metadata for every analysis
- Policy labels: keep available internally, but do not treat them as the main output contract
- Market implications: out of scope for this service; downstream tools can join this data with market and macro data later

### Inputs

Near-term:
- document URLs

Planned:
- normalized markdown scraped from websites

### Analysis hierarchy

1. Normalize raw content into a canonical document record
2. Extract semantic fingerprint for the new document
3. Compare new fingerprint to the speaker's prior document (`t-1`)
4. Compare new fingerprint to trailing `75d` and `24m` context windows
5. Compute phrase anomalies across exact, normalized, and hashed/clustered forms
6. Persist analysis artifacts for replay and auditing

## Pipeline

### 1. Normalization

Output: `NormalizedDocument`

Responsibilities:
- fetch source URL or accept pre-scraped markdown/text
- detect content type
- extract canonical text
- capture best-effort metadata: title, source, date, speaker, document type
- split transcript-like material into segments when possible
- preserve raw and cleaned forms

### 2. Fingerprinting

Output: `SemanticFingerprint`

Responsibilities:
- extract core theme assessments from a fixed-but-extensible ontology
- allow emergent themes not covered by the ontology
- preserve uncertainty explicitly
- capture evidence quotes with offsets when possible
- attach phrase signals derived from current text vs historical context
- record prompt and model versions for replay

### 3. Comparison

Output: `ComparisonResult`

Responsibilities:
- compare target document against same-speaker `t-1`
- produce window-aware orphaned concept detection
- score phrase anomalies using same-speaker history
- preserve uncertainty in the result
- summarize changes without collapsing them into market conclusions

### 4. Persistence

Required stored artifacts:
- raw source payload or canonical snapshot
- normalized document text
- extracted metadata
- analysis prompt version
- model version
- raw LLM output
- parsed fingerprint JSON
- comparison JSON
- evidence offsets and quote text

## Canonical Contracts

### `NormalizedDocument`

- `document_id`
- `source_url`
- `source_type`
- `content_type`
- `title`
- `speaker_name`
- `speech_date`
- `document_type`
- `source`
- `normalized_text`
- `segments`
- `source_metadata`
- `source_hash`

### `SemanticFingerprint`

- `document_id`
- `speaker_name`
- `speech_date`
- `document_type`
- `themes`
- `emergent_themes`
- `phrase_signals`
- `overall_tone`
- `uncertainty_notes`
- `prompt_version`
- `model_version`
- `raw_llm_response`

### `ComparisonResult`

- `comparison_id`
- `speaker_name`
- `target_document_id`
- `base_document_id`
- `comparison_type`
- `window_days`
- `theme_changes`
- `orphaned_concepts`
- `new_themes`
- `phrase_anomalies`
- `summary`
- `uncertainty_notes`

## Ontology strategy

Use a hybrid approach.

- fixed core themes for the current scaffolding
- emergent themes for novel concepts that do not fit the fixed ontology
- ability to swap in a custom ontology later without changing the rest of the pipeline

Current core themes:
- INFLATION
- LABOR_MARKETS
- GROWTH_OUTLOOK
- POLICY_STANCE
- FINANCIAL_CONDITIONS
- HOUSING
- CONSUMER_SPENDING
- GLOBAL_FACTORS
- BALANCE_SHEET
- FINANCIAL_STABILITY

## Phrase signals

Track phrase behavior at three levels:

- exact phrase
- normalized phrase
- hashed semantic key

The current implementation will scaffold with deterministic normalized phrase hashes. A richer phrase-clustering layer can be added later without changing the storage contract.

## Boilerplate handling

Boilerplate should be suppressed, not blindly deleted.

Use layered filtering:
- exact repeated stock text
- recurring low-information phrases by document type
- manually curated ignore patterns
- downgraded rather than removed when confidence is low

## Storage strategy

The existing `speeches`, `fingerprints`, and `detected_shifts` tables are useful, but not enough for replayability.

V1 storage should additionally support:
- source documents
- optional transcript segments
- phrase observations
- explicit analysis runs
- richer comparison artifacts

## Near-term implementation plan

1. Add domain models and pipeline modules under `fed_tracker/`
2. Add a v1 extraction prompt and richer extraction response contract
3. Refactor `db.py` to support analysis runs and comparison artifacts
4. Expand `schema.sql` to support auditability and phrase tracking
5. Convert `app.py` into a thin debugging client over the new pipeline
6. Keep `/poc` as legacy reference code until the new pipeline fully supersedes it
