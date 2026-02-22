-- Migration 006: SAMR adaptive feedback loop

CREATE TABLE IF NOT EXISTS samr_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL,
    org_id          UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    samr_triggered  BOOLEAN NOT NULL,
    cosine_score    FLOAT NOT NULL,
    threshold_used  FLOAT NOT NULL,
    feedback        TEXT NOT NULL CHECK (feedback IN ('correct', 'false_positive', 'false_negative')),
    submitted_by    UUID REFERENCES users(id),
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_samr_feedback_org_time
    ON samr_feedback(org_id, submitted_at DESC);

CREATE INDEX IF NOT EXISTS idx_samr_feedback_session
    ON samr_feedback(session_id);

COMMENT ON TABLE samr_feedback IS
    'Human feedback on SAMR alert correctness — drives per-org adaptive threshold learning';
COMMENT ON COLUMN samr_feedback.feedback IS
    'correct=true alert, false_positive=alert was wrong (no real issue), false_negative=missed issue';
