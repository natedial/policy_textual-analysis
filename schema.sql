-- Fed Textual Change Tracker - Database Schema
-- Supabase/PostgreSQL

-- Enable pgvector extension for future embedding support
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Speakers (Fed officials)
CREATE TABLE speakers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    title TEXT,  -- e.g., "Chair", "Vice Chair", "Governor"
    institution TEXT,  -- e.g., "Board of Governors", "New York Fed"
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name)
);

-- Speeches/Statements/Press Conferences
CREATE TABLE speeches (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    speaker_id INTEGER REFERENCES speakers(id),
    speaker_name TEXT NOT NULL,  -- Denormalized for quick access
    title TEXT,
    speech_date DATE NOT NULL,
    speech_type TEXT,  -- 'speech', 'statement', 'press_conference', 'interview'
    source TEXT,  -- 'Board of Governors', 'New York Fed', etc.
    content_type TEXT,  -- 'html', 'pdf'
    raw_text TEXT NOT NULL,
    word_count INTEGER,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Semantic Fingerprints (extracted themes)
CREATE TABLE fingerprints (
    id SERIAL PRIMARY KEY,
    speech_id INTEGER REFERENCES speeches(id) ON DELETE CASCADE,

    -- Semantic data (JSON)
    themes JSONB NOT NULL,  -- {theme_name: {stance, trajectory, emphasis, hedging, ...}}
    policy_implications JSONB NOT NULL,  -- {direction, intensity, conditionality}
    overall_tone TEXT,

    -- Extraction metadata
    model_version TEXT DEFAULT 'claude-sonnet-4-20250514',
    extraction_date TIMESTAMPTZ DEFAULT NOW(),
    prompt_version TEXT DEFAULT 'v1.0',  -- Track prompt changes

    -- Raw LLM response for debugging
    raw_llm_response TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(speech_id, model_version, prompt_version)
);

-- Detected Shifts (pairwise comparison results)
CREATE TABLE detected_shifts (
    id SERIAL PRIMARY KEY,
    speech_a_id INTEGER REFERENCES speeches(id) ON DELETE CASCADE,
    speech_b_id INTEGER REFERENCES speeches(id) ON DELETE CASCADE,
    fingerprint_a_id INTEGER REFERENCES fingerprints(id) ON DELETE CASCADE,
    fingerprint_b_id INTEGER REFERENCES fingerprints(id) ON DELETE CASCADE,

    -- Shift data (array of shift objects)
    shifts JSONB NOT NULL,  -- [{theme, shift_type, significance, from_state, to_state, interpretation, evidence}]

    -- Summary stats
    total_shifts INTEGER,
    high_significance_count INTEGER,
    medium_significance_count INTEGER,
    low_significance_count INTEGER,

    -- Metadata
    comparison_date TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(speech_a_id, speech_b_id, fingerprint_a_id, fingerprint_b_id)
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- Speeches indexes
CREATE INDEX idx_speeches_speaker_id ON speeches(speaker_id);
CREATE INDEX idx_speeches_speaker_name ON speeches(speaker_name);
CREATE INDEX idx_speeches_date ON speeches(speech_date DESC);
CREATE INDEX idx_speeches_type ON speeches(speech_type);
CREATE INDEX idx_speeches_source ON speeches(source);

-- Fingerprints indexes
CREATE INDEX idx_fingerprints_speech_id ON fingerprints(speech_id);
CREATE INDEX idx_fingerprints_extraction_date ON fingerprints(extraction_date DESC);

-- GIN index for JSONB theme queries
CREATE INDEX idx_fingerprints_themes ON fingerprints USING GIN (themes);

-- Detected shifts indexes
CREATE INDEX idx_shifts_speech_a ON detected_shifts(speech_a_id);
CREATE INDEX idx_shifts_speech_b ON detected_shifts(speech_b_id);
CREATE INDEX idx_shifts_comparison_date ON detected_shifts(comparison_date DESC);
CREATE INDEX idx_shifts_high_significance ON detected_shifts(high_significance_count) WHERE high_significance_count > 0;

-- GIN index for JSONB shift queries
CREATE INDEX idx_shifts_data ON detected_shifts USING GIN (shifts);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_speakers_updated_at BEFORE UPDATE ON speakers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_speeches_updated_at BEFORE UPDATE ON speeches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- VIEWS (Convenience queries)
-- =============================================================================

-- Recent speeches with fingerprints
CREATE VIEW recent_speeches_with_fingerprints AS
SELECT
    s.id as speech_id,
    s.url,
    s.speaker_name,
    s.title,
    s.speech_date,
    s.speech_type,
    s.source,
    f.id as fingerprint_id,
    f.themes,
    f.policy_implications,
    f.overall_tone,
    f.extraction_date
FROM speeches s
LEFT JOIN fingerprints f ON s.id = f.speech_id
ORDER BY s.speech_date DESC;

-- High significance shifts only
CREATE VIEW high_significance_shifts AS
SELECT
    ds.id,
    ds.comparison_date,
    sa.speaker_name,
    sa.speech_date as speech_a_date,
    sa.title as speech_a_title,
    sb.speech_date as speech_b_date,
    sb.title as speech_b_title,
    ds.shifts,
    ds.high_significance_count
FROM detected_shifts ds
JOIN speeches sa ON ds.speech_a_id = sa.id
JOIN speeches sb ON ds.speech_b_id = sb.id
WHERE ds.high_significance_count > 0
ORDER BY ds.comparison_date DESC;

-- =============================================================================
-- SEED DATA (Optional - common speakers)
-- =============================================================================

INSERT INTO speakers (name, title, institution) VALUES
    ('Jerome H. Powell', 'Chair', 'Board of Governors'),
    ('Philip N. Jefferson', 'Vice Chair', 'Board of Governors'),
    ('Michael S. Barr', 'Vice Chair for Supervision', 'Board of Governors'),
    ('Michelle W. Bowman', 'Governor', 'Board of Governors'),
    ('Lisa D. Cook', 'Governor', 'Board of Governors'),
    ('Adriana D. Kugler', 'Governor', 'Board of Governors'),
    ('Christopher J. Waller', 'Governor', 'Board of Governors')
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- ROW LEVEL SECURITY (Optional - for multi-user future)
-- =============================================================================

-- Enable RLS (currently permissive, can add user-specific policies later)
ALTER TABLE speakers ENABLE ROW LEVEL SECURITY;
ALTER TABLE speeches ENABLE ROW LEVEL SECURITY;
ALTER TABLE fingerprints ENABLE ROW LEVEL SECURITY;
ALTER TABLE detected_shifts ENABLE ROW LEVEL SECURITY;

-- Allow all operations for now (update when adding authentication)
CREATE POLICY "Allow all operations" ON speakers FOR ALL USING (true);
CREATE POLICY "Allow all operations" ON speeches FOR ALL USING (true);
CREATE POLICY "Allow all operations" ON fingerprints FOR ALL USING (true);
CREATE POLICY "Allow all operations" ON detected_shifts FOR ALL USING (true);

-- =============================================================================
-- COMMENTS (Documentation)
-- =============================================================================

COMMENT ON TABLE speakers IS 'Federal Reserve officials who give speeches';
COMMENT ON TABLE speeches IS 'Raw speeches, statements, and press conferences';
COMMENT ON TABLE fingerprints IS 'Extracted semantic fingerprints (themes, stances, etc.)';
COMMENT ON TABLE detected_shifts IS 'Pairwise comparison results showing detected shifts';

COMMENT ON COLUMN speeches.raw_text IS 'Full cleaned text extracted from HTML/PDF';
COMMENT ON COLUMN fingerprints.themes IS 'JSON object: {INFLATION: {stance, trajectory, emphasis, ...}, LABOR_MARKETS: {...}}';
COMMENT ON COLUMN detected_shifts.shifts IS 'Array of shift objects with evidence and interpretation';
