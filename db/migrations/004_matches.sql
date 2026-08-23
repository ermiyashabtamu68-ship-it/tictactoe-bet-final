-- ============================================================
-- Migration 004: Matches & Match Moves
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- MATCHES
-- ------------------------------------------------------------
CREATE TABLE matches (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stake_amount           NUMERIC(14,2) NOT NULL CHECK (stake_amount > 0),
    platform_fee             NUMERIC(14,2) NOT NULL DEFAULT 5.00,
    player_x_id                UUID NOT NULL REFERENCES users(internal_id) ON DELETE RESTRICT,
    player_o_id                  UUID NOT NULL REFERENCES users(internal_id) ON DELETE RESTRICT,
    current_turn                  TEXT NOT NULL DEFAULT 'X' CHECK (current_turn IN ('X', 'O')),
    board                            CHAR(9) NOT NULL DEFAULT '_________',  -- 9 cells, '_' empty, 'X'/'O' filled
    status                             TEXT NOT NULL DEFAULT 'active'
                                          CHECK (status IN ('active', 'completed_win', 'completed_draw', 'completed_forfeit', 'voided')),
    winner_id                           UUID REFERENCES users(internal_id),
    result_reason                         TEXT CHECK (result_reason IS NULL OR result_reason IN ('line', 'draw', 'timeout_forfeit', 'admin_void')),
    payout_amount                          NUMERIC(14,2),   -- amount credited to winner, NULL until settled
    settled                                  BOOLEAN NOT NULL DEFAULT false,  -- true once payout/refund txns are written; prevents double-settlement
    settled_at                                 TIMESTAMPTZ,
    last_move_at                                 TIMESTAMPTZ NOT NULL DEFAULT now(),  -- used for timeout checks
    move_timeout_seconds                           INTEGER NOT NULL DEFAULT 45,
    created_at                                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                                         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_players_different CHECK (player_x_id <> player_o_id),
    -- A match can only be settled (win/draw/forfeit/void) once - enforced again at app layer via `settled` flag + row lock
    CONSTRAINT chk_winner_requires_completed CHECK (
        (status = 'completed_win' AND winner_id IS NOT NULL) OR
        (status <> 'completed_win')
    )
);

CREATE INDEX idx_matches_status ON matches (status);
CREATE INDEX idx_matches_player_x ON matches (player_x_id);
CREATE INDEX idx_matches_player_o ON matches (player_o_id);
CREATE INDEX idx_matches_stake ON matches (stake_amount);

-- ------------------------------------------------------------
-- MATCH_MOVES
-- ------------------------------------------------------------
-- Full move history, append-only. Used for replay-protection,
-- audit, and reconstructing the board independent of the
-- `matches.board` cache column.
CREATE TABLE match_moves (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id              UUID NOT NULL REFERENCES matches(id) ON DELETE RESTRICT,
    player_id               UUID NOT NULL REFERENCES users(internal_id) ON DELETE RESTRICT,
    symbol                    TEXT NOT NULL CHECK (symbol IN ('X', 'O')),
    cell_position                SMALLINT NOT NULL CHECK (cell_position BETWEEN 0 AND 8),
    move_number                    INTEGER NOT NULL,          -- 1,2,3... sequential within match
    idempotency_key                  TEXT NOT NULL UNIQUE,      -- client-supplied or derived; prevents duplicate/replayed move requests
    created_at                         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_match_cell UNIQUE (match_id, cell_position),   -- a cell can only be played once per match
    CONSTRAINT uq_match_move_number UNIQUE (match_id, move_number)
);

CREATE INDEX idx_match_moves_match_id ON match_moves (match_id);

COMMIT;
