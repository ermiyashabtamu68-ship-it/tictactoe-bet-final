-- ============================================================
-- Migration 002: Admins
-- ============================================================

BEGIN;

CREATE TABLE admins (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username            TEXT NOT NULL UNIQUE,
    password_hash        TEXT NOT NULL,              -- bcrypt hash, never plaintext
    role                    TEXT NOT NULL DEFAULT 'admin'
                              CHECK (role IN ('super_admin', 'admin', 'finance', 'support')),
    is_active               BOOLEAN NOT NULL DEFAULT true,
    last_login_at            TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_admins_username ON admins (username);

COMMIT;
