-- ============================================================
-- Migration 003: Deposits & Withdrawals
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- DEPOSITS
-- ------------------------------------------------------------
-- Manual flow: user submits, admin verifies against real
-- Telebirr/bank records, then approves or rejects. Wallet is
-- ONLY credited on approval (handled by application logic +
-- wallet_transactions row, never here directly).
CREATE TABLE deposits (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES users(internal_id) ON DELETE RESTRICT,
    amount                 NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    payment_method          TEXT NOT NULL CHECK (payment_method IN ('telebirr', 'nib_bank')),
    reference_number         TEXT NOT NULL,         -- user-entered transaction/reference number
    screenshot_file_id         TEXT NOT NULL,         -- Telegram file_id of uploaded screenshot
    status                      TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by_admin_id         UUID REFERENCES admins(id),
    reviewed_at                    TIMESTAMPTZ,
    rejection_reason                TEXT,
    created_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_deposits_user_id ON deposits (user_id);
CREATE INDEX idx_deposits_status ON deposits (status);
-- Prevent the exact same reference number being submitted twice while pending/approved
CREATE UNIQUE INDEX idx_deposits_ref_unique ON deposits (reference_number)
    WHERE status IN ('pending', 'approved');

-- ------------------------------------------------------------
-- WITHDRAWALS
-- ------------------------------------------------------------
-- Requested amount is locked immediately on submission. Admin
-- pays manually then marks paid (debits wallet permanently) or
-- rejects (returns locked amount to available).
CREATE TABLE withdrawals (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES users(internal_id) ON DELETE RESTRICT,
    amount                 NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    payment_method          TEXT NOT NULL CHECK (payment_method IN ('telebirr', 'nib_bank')),
    payment_details           TEXT NOT NULL,         -- phone number / account number user provided
    status                      TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'paid', 'rejected')),
    reviewed_by_admin_id         UUID REFERENCES admins(id),
    reviewed_at                    TIMESTAMPTZ,
    rejection_reason                TEXT,
    created_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_withdrawals_user_id ON withdrawals (user_id);
CREATE INDEX idx_withdrawals_status ON withdrawals (status);

COMMIT;
