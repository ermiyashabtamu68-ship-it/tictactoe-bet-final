"""
match_service.py

This file runs the actual Tic-Tac-Toe game. The most important rule
in this whole file: THE SERVER DECIDES EVERYTHING. The Telegram bot
just shows buttons — it never decides who won, whose turn it is, or
whether a move is valid. It only asks this file "is this move okay?"
and this file answers based on what's actually stored in the database.

This matters because a phone app or bot button can be tampered with,
but this server code cannot be touched by a player. That's what
"server-authoritative" means, and it's what stops cheating.

Board layout (positions 0-8):
    0 | 1 | 2
    ---------
    3 | 4 | 5
    ---------
    6 | 7 | 8
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models.models import Match, MatchMove, User
from app.services import wallet_service


class InvalidMoveError(Exception):
    """Raised whenever a move breaks a rule (not your turn, cell taken, etc.)"""
    pass


class MatchNotActiveError(Exception):
    """Raised if someone tries to move in a match that already ended."""
    pass


# All 8 possible winning lines (rows, columns, diagonals)
WINNING_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # columns
    (0, 4, 8), (2, 4, 6),              # diagonals
]


def check_winner(board: str) -> str | None:
    """
    Looks at the 9-character board string and returns 'X' or 'O'
    if one of them has 3 in a row, otherwise None.
    """
    for a, b, c in WINNING_LINES:
        if board[a] != "_" and board[a] == board[b] == board[c]:
            return board[a]
    return None


def is_draw(board: str) -> bool:
    """Board is full (no '_' left) and nobody has won."""
    return "_" not in board and check_winner(board) is None


def make_move(
    db: Session,
    match_id: uuid.UUID,
    player_id: uuid.UUID,
    cell_position: int,
    idempotency_key: str,
) -> dict:
    """
    The single entry point for playing a move. The Telegram bot calls
    this every time a player taps a square.

    Every rule from the spec is enforced right here, in order:
    - match must exist and be active (not already finished)
    - it must actually be this player's turn (no moving twice in a row)
    - the cell must be empty (no overwriting a previous move)
    - duplicate/replayed requests are rejected via idempotency_key
    """
    # Lock the match row so two moves can't be processed at the same
    # instant (e.g. both players tap at the exact same millisecond).
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

    # Figure out which symbol this player controls
    if player_id == match.player_x_id:
        player_symbol = "X"
    elif player_id == match.player_o_id:
        player_symbol = "O"
    else:
        raise InvalidMoveError("This player is not part of this match.")

    # Rule: cannot make two moves in a row / must be your turn
    if match.current_turn != player_symbol:
        raise InvalidMoveError("It is not your turn.")

    # Rule: cell must be within range and empty
    if not (0 <= cell_position <= 8):
        raise InvalidMoveError("Invalid cell position.")
    if match.board[cell_position] != "_":
        raise InvalidMoveError("That cell is already taken.")

    # Rule: prevent duplicate/replayed requests (e.g. double-tap,
    # network retry sending the same request twice)
    existing = (
        db.query(MatchMove)
        .filter(MatchMove.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        # Same request seen before — return the same result, don't
        # apply the move again.
        return _build_state_response(match)

    move_number = (
        db.query(MatchMove)
        .filter(MatchMove.match_id == match_id)
        .count()
    ) + 1

    move = MatchMove(
        match_id=match_id,
        player_id=player_id,
        symbol=player_symbol,
        cell_position=cell_position,
        move_number=move_number,
        idempotency_key=idempotency_key,
    )
    db.add(move)

    # Apply the move to the cached board string
    new_board = (
        match.board[:cell_position] + player_symbol + match.board[cell_position + 1:]
    )
    match.board = new_board
    match.last_move_at = datetime.now(timezone.utc)

    # Check game-ending conditions
    winner_symbol = check_winner(new_board)
    if winner_symbol:
        winner_id = match.player_x_id if winner_symbol == "X" else match.player_o_id
        loser_id = match.player_o_id if winner_symbol == "X" else match.player_x_id
        _settle_win(db, match, winner_id, loser_id, reason="line")
    elif is_draw(new_board):
        _settle_draw(db, match)
    else:
        # Game continues — flip the turn
        match.current_turn = "O" if player_symbol == "X" else "X"

    db.commit()
    db.refresh(match)
    return _build_state_response(match)


def _settle_win(db: Session, match: Match, winner_id: uuid.UUID, loser_id: uuid.UUID, reason: str):
    """
    Marks the match as finished and pays the winner. Guarded by
    match.settled so this can never run twice on the same match
    (the row is already locked by make_move's with_for_update, so
    this check-then-act is safe from race conditions).
    """
    if match.settled:
        return  # already settled, do nothing (safety net)

    result = wallet_service.settle_match_win(
        db,
        winner_id=winner_id,
        loser_id=loser_id,
        stake_amount=match.stake_amount,
        platform_fee=match.platform_fee,
        match_id=match.id,
    )
    match.status = "completed_win" if reason in ("line", "elimination", "no_moves") else "completed_forfeit"
    match.winner_id = winner_id
    match.result_reason = reason
    match.payout_amount = result["payout"]
    match.settled = True
    match.settled_at = datetime.now(timezone.utc)


def _settle_draw(db: Session, match: Match):
    """Marks the match as drawn and fully refunds both players."""
    if match.settled:
        return

    wallet_service.settle_match_draw(
        db,
        player_a_id=match.player_x_id,
        player_b_id=match.player_o_id,
        stake_amount=match.stake_amount,
        match_id=match.id,
    )
    match.status = "completed_draw"
    match.result_reason = "draw"
    match.payout_amount = Decimal("0")
    match.settled = True
    match.settled_at = datetime.now(timezone.utc)


def check_and_apply_timeout(db: Session, match_id: uuid.UUID) -> dict | None:
    """
    Called periodically (e.g. every few seconds by a background task,
    or when a player opens the match screen) to check if the current
    player has run out of time. If so, they forfeit and the opponent
    wins — per the platform rule you chose.

    Returns the updated state if a timeout was applied, or None if
    the match is still fine / not active.
    """
    match = (
        db.query(Match)
        .filter(Match.id == match_id)
        .with_for_update()
        .first()
    )
    if match is None or match.status != "active":
        return None

    deadline = match.last_move_at + timedelta(seconds=match.move_timeout_seconds)
    if datetime.now(timezone.utc) < deadline:
        return None  # still within time, nothing to do

    # Whoever's turn it currently is has timed out
    timed_out_symbol = match.current_turn
    loser_id = match.player_x_id if timed_out_symbol == "X" else match.player_o_id
    winner_id = match.player_o_id if timed_out_symbol == "X" else match.player_x_id

    _settle_win(db, match, winner_id, loser_id, reason="timeout_forfeit")
    db.commit()
    db.refresh(match)
    return _build_state_response(match)


def _build_state_response(match: Match) -> dict:
    """Builds a clean dict describing current match state, for the bot to render."""
    return {
        "match_id": str(match.id),
        "game_type": match.game_type,
        "board": match.board,
        "current_turn": match.current_turn,
        "status": match.status,
        "winner_id": str(match.winner_id) if match.winner_id else None,
        "result_reason": match.result_reason,
        "payout_amount": str(match.payout_amount) if match.payout_amount is not None else None,
        "stake_amount": str(match.stake_amount),
        "player_x_id": str(match.player_x_id),
        "player_o_id": str(match.player_o_id),
    }
