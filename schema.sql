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
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
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
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_speakers_name ON speakers(name);
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
