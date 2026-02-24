-- Up Migration: Add organisation_id to reconciliation_sessions

ALTER TABLE reconciliation_sessions 
ADD COLUMN organisation_id VARCHAR(50);

CREATE INDEX idx_reconciliation_sessions_org_id ON reconciliation_sessions(organisation_id);

-- Down Migration
-- ALTER TABLE reconciliation_sessions DROP COLUMN organisation_id;
