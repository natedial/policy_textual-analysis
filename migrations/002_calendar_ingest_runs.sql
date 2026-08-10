-- Corpus-side tracking for calendar-driven speech ingest.
-- Calendar speaker_events.external_id is the idempotency key (separate Supabase project).

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

COMMENT ON TABLE calendar_ingest_runs IS 'Idempotent ingest state for calendar speaker_events.external_id; does not write back to the calendar project';
