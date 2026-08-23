-- ============================================================
-- Migration 007: Checkers support
-- ============================================================
-- Adds what's needed for a second game type (Checkers) alongside
-- Tic-Tac-Toe, without touching or breaking any existing data:
--   1. game_type column on matches, so we know which game a row belongs to
--   2. widen board column (Tic-Tac-Toe needs 9 chars, Checkers needs 64)
--   3. platform_fee default updated to 2.00 ETB (per owner's decision)
--   4. allow Checkers' win reasons ('elimination', 'no_moves') in result_reason
--   5. new checkers_moves table, mirroring match_moves but for Checkers

BEGIN;

-- ------------------------------------------------------------
-- 1. game_type — tags every match as 'tictactoe' or 'checkers'
-- ------------------------------------------------------------
ALTER TABLE matches ADD COLUMN game_type TEXT NOT NULL DEFAULT 'tictactoe';
CREATE INDEX idx_matches_game_type ON matches (game_type);

ALTER TABLE matches ADD CONSTRAINT chk_match_game_type
    CHECK (game_type IN ('tictactoe', 'checkers'));

-- ------------------------------------------------------------
-- 2. Widen board column
-- ------------------------------------------------------------
-- Old column was CHAR(9), fixed-width and too small for a Checkers
-- board (64 squares). Switching to VARCHAR(64) keeps existing
-- Tic-Tac-Toe rows (9-character boards) valid without any data
-- conversion — VARCHAR just allows anywhere up to 64 characters.
ALTER TABLE matches ALTER COLUMN board TYPE VARCHAR(64);

-- ------------------------------------------------------------
-- 3. Platform fee default: 5.00 -> 2.00 ETB (owner's decision)
-- ------------------------------------------------------------
-- Only changes the DEFAULT for new rows. Past matches keep
-- whatever fee was actually charged at the time — this is
-- historical data and should never silently change.
ALTER TABLE matches ALTER COLUMN platform_fee SET DEFAULT 2.00;

-- ------------------------------------------------------------
-- 4. Allow Checkers' win reasons in result_reason
-- ------------------------------------------------------------
-- The original CHECK constraint only allowed Tic-Tac-Toe's reasons
-- ('line', 'draw', 'timeout_forfeit', 'admin_void'). Checkers wins
-- via 'elimination' (opponent has no pieces left) or 'no_moves'
-- (opponent can't move) — replace the constraint to allow those too.
ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_result_reason_check;
ALTER TABLE matches ADD CONSTRAINT chk_match_result_reason
    CHECK (result_reason IS NULL OR result_reason IN (
        'line', 'draw', 'timeout_forfeit', 'admin_void', 'elimination', 'no_moves'
    ));

-- ------------------------------------------------------------
-- 5. checkers_moves — full move history for Checkers matches
-- ------------------------------------------------------------
-- Mirrors match_moves (used for Tic-Tac-Toe) but stores a
-- from/to square pair instead of a single cell, since Checkers
-- moves a piece between two squares rather than placing one mark.
CREATE TABLE checkers_moves (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id              UUID NOT NULL REFERENCES matches(id) ON DELETE RESTRICT,
    player_id               UUID NOT NULL REFERENCES users(internal_id) ON DELETE RESTRICT,
    symbol                     TEXT NOT NULL CHECK (symbol IN ('X', 'O')),
    from_position                 SMALLINT NOT NULL CHECK (from_position BETWEEN 0 AND 63),
    to_position                     SMALLINT NOT NULL CHECK (to_position BETWEEN 0 AND 63),
    move_number                       INTEGER NOT NULL,
    idempotency_key                     TEXT NOT NULL UNIQUE,
    created_at                             TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_checkers_match_move_number UNIQUE (match_id, move_number)
);

CREATE INDEX idx_checkers_moves_match_id ON checkers_moves (match_id);

COMMIT;
