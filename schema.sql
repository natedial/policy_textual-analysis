-- Fed Textual Change Tracker - V1 Schema
-- Agent-first storage for normalized documents, fingerprints, comparisons, and audit artifacts.

CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- CORE REFERENCE DATA
-- =============================================================================

CREATE TABLE IF NOT EXISTS speakers (
    id SERIAL PRIMARY KEY,
    speaker_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    title TEXT,
    institution TEXT,
    is_fomc_member BOOLEAN DEFAULT false,
    is_voting_member BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    term_start DATE,
    term_end DATE,
    name_variants JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Time-aware FOMC participation / voting membership (as-of communication date).
CREATE TABLE IF NOT EXISTS speaker_memberships (
    id SERIAL PRIMARY KEY,
    speaker_id INTEGER NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
    calendar_year INTEGER NOT NULL,
    role TEXT,
    institution TEXT,
    is_fomc_participant BOOLEAN NOT NULL DEFAULT true,
    is_voting_member BOOLEAN NOT NULL DEFAULT false,
    effective_start DATE,
    effective_end DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(speaker_id, calendar_year, role)
);

-- =============================================================================
-- SOURCE AND NORMALIZED DOCUMENTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS source_documents (
    id SERIAL PRIMARY KEY,
    source_url TEXT,
    source_type TEXT NOT NULL DEFAULT 'url',
    content_type TEXT NOT NULL DEFAULT 'unknown',
    raw_content TEXT,
    raw_markdown TEXT,
    source_hash TEXT NOT NULL,
    fetch_metadata JSONB DEFAULT '{}'::jsonb,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_hash)
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    document_key TEXT NOT NULL UNIQUE,
    source_document_id INTEGER REFERENCES source_documents(id) ON DELETE SET NULL,
    speaker_id INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
    speaker_name TEXT,
    title TEXT,
    speech_date DATE,
    document_type TEXT NOT NULL DEFAULT 'unknown',
    source TEXT,
    content_type TEXT NOT NULL DEFAULT 'unknown',
    normalized_text TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    source_metadata JSONB DEFAULT '{}'::jsonb,
    word_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_segments (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    speaker_name TEXT,
    segment_type TEXT NOT NULL DEFAULT 'body',
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, segment_index)
);

-- =============================================================================
-- ANALYSIS ARTIFACTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS analysis_runs (
    id SERIAL PRIMARY KEY,
    run_key TEXT NOT NULL UNIQUE,
    analysis_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    prompt_version TEXT,
    model_version TEXT,
    input_hash TEXT,
    raw_output TEXT,
    parsed_output JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fingerprints (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    analysis_run_id INTEGER REFERENCES analysis_runs(id) ON DELETE SET NULL,
    prompt_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    themes JSONB NOT NULL,
    emergent_themes JSONB DEFAULT '[]'::jsonb,
    phrase_signals JSONB DEFAULT '[]'::jsonb,
    overall_tone TEXT,
    uncertainty_notes JSONB DEFAULT '[]'::jsonb,
    raw_llm_response TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, prompt_version, model_version)
);

CREATE TABLE IF NOT EXISTS phrase_observations (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    speaker_id INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
    phrase_text TEXT NOT NULL,
    normalized_phrase TEXT NOT NULL,
    semantic_key TEXT NOT NULL,
    current_count INTEGER NOT NULL DEFAULT 1,
    historical_count INTEGER NOT NULL DEFAULT 0,
    rarity_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    examples JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS comparison_results (
    id SERIAL PRIMARY KEY,
    comparison_key TEXT NOT NULL UNIQUE,
    speaker_id INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
    speaker_name TEXT,
    base_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    target_document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    base_fingerprint_id INTEGER REFERENCES fingerprints(id) ON DELETE SET NULL,
    target_fingerprint_id INTEGER REFERENCES fingerprints(id) ON DELETE CASCADE,
    comparison_type TEXT NOT NULL,
    window_days INTEGER,
    theme_changes JSONB DEFAULT '[]'::jsonb,
    orphaned_concepts JSONB DEFAULT '[]'::jsonb,
    new_themes JSONB DEFAULT '[]'::jsonb,
    phrase_anomalies JSONB DEFAULT '[]'::jsonb,
    summary TEXT,
    uncertainty_notes JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- HAWK–DOVE SCORING (parallel product layer; append-only versions)
-- =============================================================================

CREATE TABLE IF NOT EXISTS hawk_dove_scores (
    id SERIAL PRIMARY KEY,
    score_key TEXT NOT NULL UNIQUE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    speaker_id INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
    speaker_name TEXT,
    speech_date DATE,
    document_type TEXT,
    source_url TEXT,
    source_hash TEXT NOT NULL,
    overall_score DOUBLE PRECISION,
    inflation_score DOUBLE PRECISION,
    labor_score DOUBLE PRECISION,
    growth_score DOUBLE PRECISION,
    policy_action_score DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    rationale TEXT,
    evidence JSONB DEFAULT '[]'::jsonb,
    section_scores JSONB DEFAULT '[]'::jsonb,
    insufficient_policy_content BOOLEAN NOT NULL DEFAULT false,
    was_voter_as_of_date BOOLEAN,
    was_fomc_participant_as_of_date BOOLEAN,
    prompt_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_parameters JSONB DEFAULT '{}'::jsonb,
    extraction_version TEXT NOT NULL DEFAULT 'v1',
    calibration_version TEXT NOT NULL DEFAULT 'none',
    analysis_run_id INTEGER REFERENCES analysis_runs(id) ON DELETE SET NULL,
    manual_override BOOLEAN NOT NULL DEFAULT false,
    override_notes TEXT,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS official_score_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_key TEXT NOT NULL UNIQUE,
    speaker_id INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
    speaker_name TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    method TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    half_life_days DOUBLE PRECISION,
    overall_score DOUBLE PRECISION,
    inflation_score DOUBLE PRECISION,
    labor_score DOUBLE PRECISION,
    growth_score DOUBLE PRECISION,
    policy_action_score DOUBLE PRECISION,
    communication_count INTEGER NOT NULL DEFAULT 0,
    coverage_notes JSONB DEFAULT '{}'::jsonb,
    score_keys JSONB DEFAULT '[]'::jsonb,
    prompt_version TEXT,
    model_version TEXT,
    calibration_version TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS committee_score_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_key TEXT NOT NULL UNIQUE,
    as_of_date DATE NOT NULL,
    cohort TEXT NOT NULL,
    method TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    half_life_days DOUBLE PRECISION,
    overall_score DOUBLE PRECISION,
    official_count INTEGER NOT NULL DEFAULT 0,
    communication_count INTEGER NOT NULL DEFAULT 0,
    coverage_notes JSONB DEFAULT '{}'::jsonb,
    official_scores JSONB DEFAULT '[]'::jsonb,
    prompt_version TEXT,
    model_version TEXT,
    calibration_version TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_speakers_name ON speakers(name);
CREATE INDEX IF NOT EXISTS idx_speaker_memberships_speaker ON speaker_memberships(speaker_id);
CREATE INDEX IF NOT EXISTS idx_speaker_memberships_year ON speaker_memberships(calendar_year);
CREATE INDEX IF NOT EXISTS idx_hawk_dove_document_id ON hawk_dove_scores(document_id);
CREATE INDEX IF NOT EXISTS idx_hawk_dove_speaker_name ON hawk_dove_scores(speaker_name);
CREATE INDEX IF NOT EXISTS idx_hawk_dove_speech_date ON hawk_dove_scores(speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_hawk_dove_versions ON hawk_dove_scores(document_id, prompt_version, model_version, calibration_version);
CREATE INDEX IF NOT EXISTS idx_official_snapshots_speaker ON official_score_snapshots(speaker_name, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_committee_snapshots_date ON committee_score_snapshots(as_of_date DESC, cohort);
CREATE INDEX IF NOT EXISTS idx_documents_speaker_name ON documents(speaker_name);
CREATE INDEX IF NOT EXISTS idx_documents_speech_date ON documents(speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_source_hash ON documents(source_hash);
CREATE INDEX IF NOT EXISTS idx_segments_document_id ON document_segments(document_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_target ON analysis_runs(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_fingerprints_document_id ON fingerprints(document_id);
CREATE INDEX IF NOT EXISTS idx_fingerprints_themes ON fingerprints USING GIN (themes);
CREATE INDEX IF NOT EXISTS idx_phrase_obs_semantic_key ON phrase_observations(semantic_key);
CREATE INDEX IF NOT EXISTS idx_phrase_obs_rarity ON phrase_observations(rarity_score DESC);
CREATE INDEX IF NOT EXISTS idx_comparison_target_doc ON comparison_results(target_document_id);
CREATE INDEX IF NOT EXISTS idx_comparison_speaker_name ON comparison_results(speaker_name);
CREATE INDEX IF NOT EXISTS idx_comparison_type ON comparison_results(comparison_type);
CREATE INDEX IF NOT EXISTS idx_comparison_theme_changes ON comparison_results USING GIN (theme_changes);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_speakers_updated_at ON speakers;
CREATE TRIGGER update_speakers_updated_at BEFORE UPDATE ON speakers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- VIEWS
-- =============================================================================

CREATE OR REPLACE VIEW recent_documents_with_fingerprints AS
SELECT
    d.id AS document_id,
    d.document_key,
    d.speaker_name,
    d.title,
    d.speech_date,
    d.document_type,
    d.source,
    d.source_hash,
    f.id AS fingerprint_id,
    f.prompt_version,
    f.model_version,
    f.themes,
    f.emergent_themes,
    f.phrase_signals,
    f.overall_tone,
    f.created_at AS fingerprint_created_at
FROM documents d
LEFT JOIN fingerprints f ON d.id = f.document_id
ORDER BY d.speech_date DESC NULLS LAST, d.created_at DESC;

CREATE OR REPLACE VIEW latest_comparison_results AS
SELECT
    c.id,
    c.comparison_key,
    c.speaker_name,
    c.comparison_type,
    c.window_days,
    c.summary,
    c.created_at,
    base.title AS base_title,
    base.speech_date AS base_date,
    target.title AS target_title,
    target.speech_date AS target_date
FROM comparison_results c
LEFT JOIN documents base ON c.base_document_id = base.id
LEFT JOIN documents target ON c.target_document_id = target.id
ORDER BY c.created_at DESC;

CREATE OR REPLACE VIEW latest_hawk_dove_scores AS
SELECT DISTINCT ON (s.document_id, s.prompt_version, s.model_version, s.calibration_version)
    s.*
FROM hawk_dove_scores s
ORDER BY s.document_id, s.prompt_version, s.model_version, s.calibration_version, s.scored_at DESC, s.id DESC;

CREATE OR REPLACE VIEW recent_hawk_dove_observations AS
SELECT
    s.id,
    s.score_key,
    s.speaker_name,
    s.speech_date,
    s.document_type,
    s.source_url,
    s.overall_score,
    s.inflation_score,
    s.labor_score,
    s.growth_score,
    s.policy_action_score,
    s.confidence,
    s.insufficient_policy_content,
    s.was_voter_as_of_date,
    s.prompt_version,
    s.model_version,
    s.calibration_version,
    s.scored_at,
    d.title,
    d.document_key
FROM hawk_dove_scores s
LEFT JOIN documents d ON s.document_id = d.id
WHERE s.insufficient_policy_content = false
ORDER BY s.speech_date DESC NULLS LAST, s.scored_at DESC;

CREATE OR REPLACE VIEW official_hawk_dove_timeseries AS
SELECT
    speaker_name,
    as_of_date,
    overall_score,
    inflation_score,
    labor_score,
    growth_score,
    policy_action_score,
    communication_count,
    method,
    window_days,
    half_life_days,
    prompt_version,
    model_version,
    calibration_version,
    coverage_notes,
    snapshot_key,
    created_at
FROM official_score_snapshots
ORDER BY speaker_name, as_of_date, model_version;

CREATE OR REPLACE VIEW committee_hawk_dove_timeseries AS
SELECT
    cohort,
    as_of_date,
    overall_score,
    official_count,
    communication_count,
    method,
    window_days,
    half_life_days,
    prompt_version,
    model_version,
    calibration_version,
    coverage_notes,
    snapshot_key,
    created_at
FROM committee_score_snapshots
ORDER BY cohort, as_of_date, model_version;

-- =============================================================================
-- CALENDAR-DRIVEN INGEST (corpus-side status; calendar project is read-only)
-- =============================================================================

CREATE TABLE IF NOT EXISTS calendar_ingest_runs (
    id SERIAL PRIMARY KEY,
    external_id TEXT NOT NULL,
    calendar_event_id INTEGER,
    speaker_name TEXT,
    title TEXT,
    scheduled_start TIMESTAMPTZ,
    event_type TEXT,
    source TEXT,
    resolved_url TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    document_key TEXT,
    score_key TEXT,
    model_version TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    scored_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (external_id)
);

CREATE INDEX IF NOT EXISTS idx_calendar_ingest_runs_status ON calendar_ingest_runs(status);
CREATE INDEX IF NOT EXISTS idx_calendar_ingest_runs_scheduled_start ON calendar_ingest_runs(scheduled_start DESC);

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE source_documents IS 'Raw fetched or scraped source payloads before normalization';
COMMENT ON TABLE documents IS 'Canonical normalized Fed communications used for analysis';
COMMENT ON TABLE document_segments IS 'Optional speaker-turn or paragraph-level segmentation for transcripts';
COMMENT ON TABLE analysis_runs IS 'Replay metadata for extraction and comparison runs';
COMMENT ON TABLE fingerprints IS 'Structured semantic fingerprint artifacts for a normalized document';
COMMENT ON TABLE phrase_observations IS 'Phrase-level rarity and anomaly records by document';
COMMENT ON TABLE comparison_results IS 'Structured comparison artifacts between documents or windows';
COMMENT ON TABLE speaker_memberships IS 'Time-aware FOMC participation and voting status by year/term';
COMMENT ON TABLE hawk_dove_scores IS 'Append-only hawk-dove score observations; never overwrite on rescore';
COMMENT ON TABLE official_score_snapshots IS 'Versioned official-level aggregate hawk-dove scores';
COMMENT ON TABLE committee_score_snapshots IS 'Versioned committee/cohort aggregate hawk-dove scores';
COMMENT ON TABLE calendar_ingest_runs IS 'Idempotent ingest state for calendar speaker_events.external_id; does not write back to the calendar project';
