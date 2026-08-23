-- ============================================================
-- Migration 001: Core schema for TicTacToe Betting Platform
-- ============================================================
-- Run order matters. This is migration 1 of N.

BEGIN;

-- Needed for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ------------------------------------------------------------
-- USERS
-- ------------------------------------------------------------
-- Telegram user ID is the login identifier, but NOT the
-- permanent internal identifier. internal_id (UUID) is what
-- every other table references.
CREATE TABLE users (
    internal_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id     BIGINT NOT NULL UNIQUE,
    telegram_username    TEXT,                 -- can change, never used as FK
    display_name         TEXT,
    status                TEXT NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'suspended', 'self_excluded', 'banned')),
    date_of_birth         DATE,                 -- for age verification, nullable until KYC done
    country_code          TEXT,                 -- ISO 3166-1 alpha-2, for geo restriction checks
    kyc_status            TEXT NOT NULL DEFAULT 'not_required'
                              CHECK (kyc_status IN ('not_required', 'pending', 'verified', 'rejected')),
    self_exclusion_until  TIMESTAMPTZ,           -- if set and in future, user cannot play/deposit
    registered_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_telegram_user_id ON users (telegram_user_id);
CREATE INDEX idx_users_status ON users (status);

-- ------------------------------------------------------------
-- WALLETS
-- ------------------------------------------------------------
-- One wallet per user. Balances are derived/cached here but the
-- source of truth for every change is wallet_transactions.
-- available_balance + locked_balance must never go negative.
CREATE TABLE wallets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL UNIQUE REFERENCES users(internal_id) ON DELETE RESTRICT,
    available_balance    NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (available_balance >= 0),
    locked_balance        NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (locked_balance >= 0),
    total_winnings         NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_games             INTEGER NOT NULL DEFAULT 0,
    total_deposits          NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_withdrawals       NUMERIC(14,2) NOT NULL DEFAULT 0,
    version                 INTEGER NOT NULL DEFAULT 0,  -- optimistic locking
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_wallets_user_id ON wallets (user_id);

-- ------------------------------------------------------------
-- WALLET_TRANSACTIONS
-- ------------------------------------------------------------
-- Immutable ledger. Every balance change (deposit approval,
-- withdrawal, stake lock, stake release, payout, refund, fee,
-- admin adjustment) creates exactly one row here. Rows are
-- never updated or deleted.
CREATE TABLE wallet_transactions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_id           UUID NOT NULL REFERENCES wallets(id) ON DELETE RESTRICT,
    type                 TEXT NOT NULL CHECK (type IN (
                              'deposit',              -- approved deposit credited
                              'withdrawal',            -- approved withdrawal debited
                              'stake_lock',             -- moved available -> locked for a match
                              'stake_release',           -- match voided/refund: locked -> available
                              'payout',                  -- match win: locked -> available (net of fee)
                              'fee',                      -- platform fee recorded (informational, non-wallet-moving on user side)
                              'draw_refund',               -- draw: locked -> available, full stake back
                              'admin_adjustment'            -- manual correction, always audited
                          )),
    amount                NUMERIC(14,2) NOT NULL,       -- positive = credit to available, negative = debit
    balance_after          NUMERIC(14,2) NOT NULL,       -- available_balance snapshot after this txn
    locked_after            NUMERIC(14,2) NOT NULL,       -- locked_balance snapshot after this txn
    reference_type           TEXT CHECK (reference_type IN ('deposit', 'withdrawal', 'match', 'admin')),
    reference_id              UUID,                        -- FK-like pointer to deposits/withdrawals/matches/admins (not enforced, polymorphic)
    idempotency_key            TEXT NOT NULL UNIQUE,        -- prevents double-processing of the same event
    description                 TEXT,
    created_by_admin_id          UUID,                       -- set only for admin_adjustment
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_wallet_txn_wallet_id ON wallet_transactions (wallet_id);
CREATE INDEX idx_wallet_txn_reference ON wallet_transactions (reference_type, reference_id);
CREATE INDEX idx_wallet_txn_created_at ON wallet_transactions (created_at);

COMMIT;
