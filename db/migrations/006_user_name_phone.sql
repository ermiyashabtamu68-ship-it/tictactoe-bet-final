-- ============================================================
-- Migration 006: Add full_name and phone_number to users
-- ============================================================
-- Collected during registration instead of relying only on
-- Telegram's own name/username, which the user can change anytime.

BEGIN;

ALTER TABLE users ADD COLUMN full_name TEXT;
ALTER TABLE users ADD COLUMN phone_number TEXT;

-- A phone number should only be tied to one account, to make it
-- harder for one person to spin up unlimited accounts.
CREATE UNIQUE INDEX idx_users_phone_number ON users (phone_number) WHERE phone_number IS NOT NULL;

COMMIT;
