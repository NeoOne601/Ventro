-- ============================================================
-- Migration 001: Users and Organisations tables
-- Run once on initial database setup
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Organisations (multi-tenancy root)
CREATE TABLE IF NOT EXISTS organisations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,
    plan            VARCHAR(50) NOT NULL DEFAULT 'enterprise',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organisation_id     UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    email               VARCHAR(320) NOT NULL,
    full_name           VARCHAR(255) NOT NULL DEFAULT '',
    hashed_password     TEXT NOT NULL,
    role                VARCHAR(50) NOT NULL DEFAULT 'ap_analyst'
                            CHECK (role IN ('external_auditor','ap_analyst','ap_manager',
                                            'finance_director','admin','developer','master')),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at       TIMESTAMPTZ,
    UNIQUE (organisation_id, email)      -- email unique per org (not globally)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_org   ON users (organisation_id);

-- Refresh token store (JWT rotation)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,    -- SHA-256 of the raw token
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_agent      TEXT,
    ip_address      INET
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);

-- Immutable Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    organisation_id UUID REFERENCES organisations(id),
    user_id         UUID REFERENCES users(id),
    action          VARCHAR(100) NOT NULL,    -- e.g. "session.created", "finding.overridden"
    resource_type   VARCHAR(50),              -- e.g. "session", "document"
    resource_id     UUID,
    details         JSONB,
    ip_address      INET,
    prev_hash       CHAR(64),                 -- SHA-256 of previous row (chain integrity)
    row_hash        CHAR(64) NOT NULL,        -- SHA-256(id||org||user||action||details||prev_hash)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit log is append-only: revoke all UPDATE/DELETE on this table
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

-- Seed: default organisation for development
INSERT INTO organisations (id, name, slug, plan)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Ventro Development',
    'dev',
    'enterprise'
) ON CONFLICT DO NOTHING;
