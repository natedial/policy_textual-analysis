-- Additive hawk-dove schema for existing deployments.
-- Safe to run after the base V1 schema.sql.

ALTER TABLE speakers
    ADD COLUMN IF NOT EXISTS is_voting_member BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS term_start DATE,
    ADD COLUMN IF NOT EXISTS term_end DATE,
    ADD COLUMN IF NOT EXISTS name_variants JSONB DEFAULT '[]'::jsonb;

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

CREATE INDEX IF NOT EXISTS idx_speaker_memberships_speaker ON speaker_memberships(speaker_id);
CREATE INDEX IF NOT EXISTS idx_speaker_memberships_year ON speaker_memberships(calendar_year);
CREATE INDEX IF NOT EXISTS idx_hawk_dove_document_id ON hawk_dove_scores(document_id);
CREATE INDEX IF NOT EXISTS idx_hawk_dove_speaker_name ON hawk_dove_scores(speaker_name);
CREATE INDEX IF NOT EXISTS idx_hawk_dove_speech_date ON hawk_dove_scores(speech_date DESC);
CREATE INDEX IF NOT EXISTS idx_hawk_dove_versions ON hawk_dove_scores(document_id, prompt_version, model_version, calibration_version);
CREATE INDEX IF NOT EXISTS idx_official_snapshots_speaker ON official_score_snapshots(speaker_name, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_committee_snapshots_date ON committee_score_snapshots(as_of_date DESC, cohort);

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
