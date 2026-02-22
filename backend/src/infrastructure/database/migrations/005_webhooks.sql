-- Migration: Webhook endpoints and delivery log
-- Run after existing migrations

CREATE TABLE IF NOT EXISTS webhook_endpoints (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    secret      TEXT NOT NULL,                     -- HMAC signing secret (stored encrypted)
    description TEXT NOT NULL DEFAULT '',
    events      TEXT[] NOT NULL DEFAULT '{}',      -- e.g. ARRAY['reconciliation.completed']
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  UUID REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_org ON webhook_endpoints(org_id);
CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_active ON webhook_endpoints(org_id, is_active);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id UUID NOT NULL REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
    event       TEXT NOT NULL,
    payload     JSONB NOT NULL,
    status_code INT,
    attempt     INT NOT NULL DEFAULT 1,
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_endpoint ON webhook_deliveries(endpoint_id, delivered_at DESC);

COMMENT ON TABLE webhook_endpoints   IS 'Registered outbound webhook URLs per organisation';
COMMENT ON TABLE webhook_deliveries  IS 'Full delivery log — every attempt, success or failure';
