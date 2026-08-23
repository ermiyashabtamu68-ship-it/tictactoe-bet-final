"""
services/checkers_service.py

Checkers using SIMPLE rules (as chosen for this platform): captures
are OPTIONAL (not forced), only single jumps (no chained multi-jump
captures), kings move any diagonal direction, men move/capture
forward only. A win happens when the opponent has no pieces left, or
when it becomes their turn and they have no legal move at all.

Board representation: a 64-character string, one char per square,
row-major (row 0 = top, row 7 = bottom, 8 squares per row):
  '.' = light square, never used, always empty
  '_' = empty dark (playable) square
  'x' = Player X's man     'X' = Player X's king   (X moves toward row 7)
  'o' = Player O's man     'O' = Player O's king   (O moves toward row 0)

This file deliberately reuses match_service's _settle_win/_settle_draw/
_build_state_response and wallet_service under the hood (via
match_service) instead of duplicating money-handling logic — that
code is already tested for Tic-Tac-Toe and works unchanged here,
since it only cares about winner_id/loser_id/stake, not the board.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Match, CheckersMove
from app.services.match_service import (
    InvalidMoveError,
    MatchNotActiveError,
    _settle_win,
    _build_state_response,
)

BOARD_SIZE = 8


def _idx(row: int, col: int) -> int:
    return row * BOARD_SIZE + col


def _rc(pos: int) -> tuple[int, int]:
    return divmod(pos, BOARD_SIZE)


def initial_board() -> str:
    """Standard starting position: 12 men per side on the dark squares."""
    squares = ["."] * 64
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if (row + col) % 2 == 1:
                if row <= 2:
                    squares[_idx(row, col)] = "x"
                elif row >= 5:
                    squares[_idx(row, col)] = "o"
                else:
                    squares[_idx(row, col)] = "_"
    return "".join(squares)


def _owner(ch: str) -> str | None:
    if ch in ("x", "X"):
        return "X"
    if ch in ("o", "O"):
        return "O"
    return None


def _is_king(ch: str) -> bool:
    return ch in ("X", "O")


def _forward_dir(symbol: str) -> int:
    return 1 if symbol == "X" else -1


def legal_moves_for(board: str, symbol: str) -> list[tuple[int, int]]:
    """
    Every legal (from_position, to_position) pair for `symbol` —
    simple diagonal moves and single captures. Captures are NOT
    forced (per the simple ruleset), so this list mixes both kinds
    and the player can pick any of them.
    """
    moves = []
    for pos in range(64):
        ch = board[pos]
        if _owner(ch) != symbol:
            continue
        row, col = _rc(pos)
        directions = (
            [(-1, -1), (-1, 1), (1, -1), (1, 1)]
            if _is_king(ch)
            else [(_forward_dir(symbol), -1), (_forward_dir(symbol), 1)]
        )
        for dr, dc in directions:
            r1, c1 = row + dr, col + dc
            if not (0 <= r1 < BOARD_SIZE and 0 <= c1 < BOARD_SIZE):
                continue
            target = board[_idx(r1, c1)]
            if target == "_":
                moves.append((pos, _idx(r1, c1)))
            elif _owner(target) not in (None, symbol):
                r2, c2 = row + 2 * dr, col + 2 * dc
                if 0 <= r2 < BOARD_SIZE and 0 <= c2 < BOARD_SIZE and board[_idx(r2, c2)] == "_":
                    moves.append((pos, _idx(r2, c2)))
    return moves


def make_move(
    db: Session,
    match_id: uuid.UUID,
    player_id: uuid.UUID,
    from_position: int,
    to_position: int,
    idempotency_key: str,
) -> dict:
    match = (
        db.query(Match)
        .filter(Match.id == match_id)
        .with_for_update()
        .first()
    )
    if match is None:
        raise ValueError(f"Match {match_id} not found.")
    if match.status != "active":
        raise MatchNotActiveError(f"Match {match_id} is not active (status={match.status}).")

    if player_id == match.player_x_id:
        symbol = "X"
    elif player_id == match.player_o_id:
        symbol = "O"
    else:
        raise InvalidMoveError("You are not a player in this match.")

    if match.current_turn != symbol:
        raise InvalidMoveError("It's not your turn.")

    # Idempotency: if this exact request was already applied (e.g.
    # a retried network request), just return the current state
    # instead of applying the move a second time.
    existing = (
        db.query(CheckersMove)
        .filter(CheckersMove.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        return _build_state_response(match)

    if not (0 <= from_position < 64) or not (0 <= to_position < 64):
        raise InvalidMoveError("Move is out of bounds.")

    board_chars = list(match.board)
    piece = board_chars[from_position]
    if _owner(piece) != symbol:
        raise InvalidMoveError("That's not your piece.")

    legal = legal_moves_for(match.board, symbol)
    if (from_position, to_position) not in legal:
        raise InvalidMoveError("That move isn't allowed.")

    from_row, from_col = _rc(from_position)
    to_row, to_col = _rc(to_position)

    board_chars[to_position] = piece
    board_chars[from_position] = "_"

    if abs(to_row - from_row) == 2:
        mid_row = (from_row + to_row) // 2
        mid_col = (from_col + to_col) // 2
        board_chars[_idx(mid_row, mid_col)] = "_"  # captured piece removed

    back_row = 7 if symbol == "X" else 0
    if to_row == back_row and not _is_king(piece):
        board_chars[to_position] = piece.upper()  # promote to king

    new_board = "".join(board_chars)
    match.board = new_board
    match.last_move_at = datetime.now(timezone.utc)

    move_number = (
        db.query(CheckersMove)
        .filter(CheckersMove.match_id == match_id)
        .count()
    ) + 1
    db.add(CheckersMove(
        match_id=match_id,
        player_id=player_id,
        symbol=symbol,
        from_position=from_position,
        to_position=to_position,
        move_number=move_number,
        idempotency_key=idempotency_key,
    ))

    opponent_symbol = "O" if symbol == "X" else "X"
    opponent_id = match.player_o_id if symbol == "X" else match.player_x_id

    opponent_pieces_left = sum(1 for c in new_board if _owner(c) == opponent_symbol)
    if opponent_pieces_left == 0:
        _settle_win(db, match, winner_id=player_id, loser_id=opponent_id, reason="elimination")
    elif not legal_moves_for(new_board, opponent_symbol):
        _settle_win(db, match, winner_id=player_id, loser_id=opponent_id, reason="no_moves")
    else:
        match.current_turn = opponent_symbol

    db.commit()
    db.refresh(match)
    return _build_state_response(match)
