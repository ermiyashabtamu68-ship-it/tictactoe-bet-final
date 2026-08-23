-- ============================================================
-- Migration 005: Audit Logs & Platform Configuration
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- AUDIT_LOGS
-- ------------------------------------------------------------
-- Records every sensitive action: admin approvals/rejections,
-- balance adjustments, suspensions, config changes, etc.
-- Append-only, never edited or deleted.
CREATE TABLE audit_logs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type              TEXT NOT NULL CHECK (actor_type IN ('admin', 'system', 'user')),
    actor_id                  UUID,                       -- admins.id or users.internal_id depending on actor_type
    action                       TEXT NOT NULL,              -- e.g. 'deposit_approved', 'withdrawal_rejected', 'user_suspended', 'config_updated'
    target_type                   TEXT,                      -- e.g. 'deposit', 'withdrawal', 'user', 'match', 'config'
    target_id                       UUID,
    metadata                          JSONB,                  -- before/after values, reasons, IP, etc.
    created_at                          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_logs_actor ON audit_logs (actor_type, actor_id);
CREATE INDEX idx_audit_logs_target ON audit_logs (target_type, target_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs (created_at);

-- ------------------------------------------------------------
-- PLATFORM_CONFIG
-- ------------------------------------------------------------
-- Single-row-per-key config table, editable from admin panel.
-- Every change should also write an audit_logs row.
CREATE TABLE platform_config (
    key                   TEXT PRIMARY KEY,
    value                   TEXT NOT NULL,
    description               TEXT,
    updated_by_admin_id         UUID REFERENCES admins(id),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO platform_config (key, value, description) VALUES
    ('platform_fee_etb', '5.00', 'Fixed fee in ETB charged per completed match'),
    ('stake_tiers_etb', '10,20,50,100', 'Comma-separated allowed stake amounts'),
    ('move_timeout_seconds', '45', 'Seconds allowed per move before forfeit'),
    ('min_age', '18', 'Minimum age to register/play'),
    ('allowed_country_codes', 'ET', 'Comma-separated ISO country codes allowed to play'),
    ('kyc_required_above_etb', '5000', 'Cumulative deposit/withdrawal amount that triggers KYC requirement'),
    ('daily_deposit_limit_etb', '5000', 'Max total deposits per user per day'),
    ('daily_withdrawal_limit_etb', '5000', 'Max total withdrawals per user per day'),
    ('draw_policy', 'full_refund_no_fee', 'Draw outcome: both players fully refunded, no platform fee charged');

COMMIT;
