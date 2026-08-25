"""
matchmaking_service.py

This file handles finding an opponent. When a player picks a stake
(e.g. 50 ETB) and presses Play, we need to find another player who
picked the SAME stake and is also waiting.

We use Redis for this, not the main database. Why? Because matching
players needs to be FAST and happen in real-time, and Redis is built
exactly for this kind of temporary "who's waiting right now" data.
The database (Postgres) is for permanent records; Redis is for
short-lived, fast-changing state.

How it works, step by step:
1. Player A picks 50 ETB -> we check: is anyone else already
   waiting at 50 ETB?
2. If yes -> pair them immediately, remove both from the queue,
   lock both stakes, create the match.
3. If no -> add Player A to the "waiting at 50 ETB" queue, and they
   wait for someone else to come along.

We use Redis's atomic operations so that if two players press Play
at the exact same millisecond, they still can't both "match with
themselves" or get double-matched.
"""

import json
import uuid
from decimal import Decimal
from datetime import datetime, timezone

import redis
from sqlalchemy.orm import Session

from app.models.models import Match
from app.services import wallet_service

# One Redis list per stake tier acts as a waiting queue.
# Key looks like: "matchmaking:queue:50"
QUEUE_KEY_PREFIX = "matchmaking:queue:"

# How long (seconds) a player can sit in the queue before we
# consider them "gone" (e.g. they closed Telegram). The bot should
# also let them cancel manually.
QUEUE_ENTRY_TTL_SECONDS = 120


class AlreadyInQueueError(Exception):
    pass


class InsufficientBalanceForStakeError(Exception):
    pass


# ---------------- Friend challenges ----------------
# Separate from the random matchmaking queue above. A challenge is
# stored per OPPONENT USERNAME (not stake tier), since it's aimed at
# one specific person rather than "anyone at this stake".

CHALLENGE_KEY_PREFIX = "matchmaking:challenge:"
CHALLENGE_TTL_SECONDS = 120  # friend has 2 minutes to accept/decline


class OpponentNotFoundError(Exception):
    pass


class CannotChallengeSelfError(Exception):
    pass


class ChallengeNotFoundError(Exception):
    pass


def _queue_key(stake_amount: Decimal, game_type: str = "tictactoe") -> str:
    return f"{QUEUE_KEY_PREFIX}{game_type}:{stake_amount}"


def _challenge_key(username: str) -> str:
    return f"{CHALLENGE_KEY_PREFIX}{username.strip().lstrip('@').lower()}"


def create_challenge(redis_client, db: Session, challenger, opponent_username: str, stake_amount: Decimal, game_type: str = "tictactoe") -> dict:
    """
    Called when Player A wants to challenge a specific friend by
    their @username. Checks the challenger can afford the stake,
    looks up the opponent, and stores the pending challenge in Redis
    keyed by the OPPONENT's username so their side can find it when
    they respond. The opponent's balance is only checked when they
    actually accept (it may change in the meantime).
    """
    from app.services.user_service import get_user_by_username
    from app.services import wallet_service

    opponent = get_user_by_username(db, opponent_username)
    if opponent is None:
        raise OpponentNotFoundError(f"No registered player found with username '{opponent_username}'.")

    if opponent.internal_id == challenger.internal_id:
        raise CannotChallengeSelfError("You can't challenge yourself.")

    wallet = db.query(wallet_service.Wallet).filter(
        wallet_service.Wallet.user_id == challenger.internal_id
    ).first()
    if wallet is None or wallet.available_balance < stake_amount:
        raise InsufficientBalanceForStakeError(
            f"User {challenger.internal_id} does not have {stake_amount} ETB available."
        )

    entry = {
        "challenger_id": str(challenger.internal_id),
        "challenger_telegram_id": challenger.telegram_user_id,
        "challenger_username": challenger.telegram_username,
        "stake_amount": str(stake_amount),
        "game_type": game_type,
    }
    redis_client.set(_challenge_key(opponent.telegram_username), json.dumps(entry), ex=CHALLENGE_TTL_SECONDS)

    return {
        "opponent_telegram_id": opponent.telegram_user_id,
        "opponent_username": opponent.telegram_username,
    }


def respond_challenge(redis_client, db: Session, responder, accept: bool) -> dict:
    """
    Called when the challenged friend presses Accept or Decline.
    We look up the challenge by the RESPONDER's own username (that's
    how it was stored). On accept, reuses _create_match — the exact
    same stake-locking logic random matchmaking uses, so there's no
    separate code path that could drift out of sync or be less safe.
    """
    if not responder.telegram_username:
        raise ChallengeNotFoundError("No pending challenge found.")

    key = _challenge_key(responder.telegram_username)
    raw = redis_client.get(key)
    if raw is None:
        raise ChallengeNotFoundError("No pending challenge found (it may have expired).")

    redis_client.delete(key)
    data = json.loads(raw)
    challenger_telegram_id = data["challenger_telegram_id"]

    if not accept:
        return {"status": "declined", "challenger_telegram_id": challenger_telegram_id}

    stake_amount = Decimal(data["stake_amount"])
    challenger_id = uuid.UUID(data["challenger_id"])
    game_type = data.get("game_type", "tictactoe")

    match = _create_match(
        db, player_a_id=challenger_id, player_b_id=responder.internal_id,
        stake_amount=stake_amount, game_type=game_type,
    )
    return {
        "status": "matched",
        "match_id": str(match.id),
        "challenger_telegram_id": challenger_telegram_id,
    }


def join_queue(
    redis_client: redis.Redis,
    db: Session,
    user_id: uuid.UUID,
    stake_amount: Decimal,
    game_type: str = "tictactoe",
) -> dict:
    """
    Called when a player picks a stake and presses Play.

    Returns one of two things:
      {"status": "waiting"}                     -> no opponent yet, added to queue
      {"status": "matched", "match_id": "..."}   -> opponent found, match created

    `game_type` keeps Tic-Tac-Toe and Checkers players in separate
    queues (a checkers player will never be paired with someone
    waiting for tic-tac-toe, even at the same stake).
    """
    from app.services.wallet_service import _get_locked_wallet  # local import avoids circulars

    key = _queue_key(stake_amount, game_type)

    # Use a Redis lock so two simultaneous join_queue calls (from two
    # different players, or the same player double-tapping) can't
    # both read the queue as "empty" and both add themselves.
    lock = redis_client.lock(f"matchmaking:lock:{game_type}:{stake_amount}", timeout=10)
    with lock:
        # Is there already someone waiting at this stake?
        waiting_entry = redis_client.lpop(key)

        if waiting_entry is None:
            # Nobody waiting — check balance BEFORE adding to queue,
            # so we never queue someone who can't actually afford it.
            wallet = db.query(wallet_service.Wallet).filter(
                wallet_service.Wallet.user_id == user_id
            ).first()
            if wallet is None or wallet.available_balance < stake_amount:
                raise InsufficientBalanceForStakeError(
                    f"User {user_id} does not have {stake_amount} ETB available."
                )

            entry = {
                "user_id": str(user_id),
                "joined_at": datetime.now(timezone.utc).isoformat(),
            }
            redis_client.rpush(key, json.dumps(entry))
            redis_client.expire(key, QUEUE_ENTRY_TTL_SECONDS)
            return {"status": "waiting"}

        # Someone was waiting — pair them up.
        opponent_data = json.loads(waiting_entry)
        opponent_id = uuid.UUID(opponent_data["user_id"])

        # Edge case: a player queued against themselves (e.g. opened
        # two sessions). Don't allow self-matching — put the other
        # entry back and add the new one instead.
        if opponent_id == user_id:
            redis_client.rpush(key, waiting_entry)
            return join_queue(redis_client, db, user_id, stake_amount, game_type)

        match = _create_match(
            db, player_a_id=opponent_id, player_b_id=user_id,
            stake_amount=stake_amount, game_type=game_type,
        )
        return {"status": "matched", "match_id": str(match.id)}


def leave_queue(redis_client: redis.Redis, user_id: uuid.UUID, stake_amount: Decimal, game_type: str = "tictactoe") -> bool:
    """
    Called if a player cancels while waiting (presses Cancel/Back).
    Returns True if they were removed, False if they weren't in the queue
    (e.g. they'd already been matched).
    """
    key = _queue_key(stake_amount, game_type)
    lock = redis_client.lock(f"matchmaking:lock:{game_type}:{stake_amount}", timeout=10)
    with lock:
        raw_items = redis_client.lrange(key, 0, -1)
        for raw in raw_items:
            data = json.loads(raw)
            if data["user_id"] == str(user_id):
                redis_client.lrem(key, 1, raw)
                return True
    return False


def check_if_matched(db: Session, user_id: uuid.UUID) -> Match | None:
    """
    Looks for an ACTIVE match this user is currently part of.
    Used by the bot's polling loop to check "has someone matched
    with me yet?" WITHOUT the side-effects of calling join_queue
    again (which would pop/re-push queue entries unnecessarily).
    This is the clean way to check status while waiting.
    """
    return (
        db.query(Match)
        .filter(
            Match.status == "active",
            (Match.player_x_id == user_id) | (Match.player_o_id == user_id),
        )
        .order_by(Match.created_at.desc())
        .first()
    )


def _create_match(
    db: Session, player_a_id: uuid.UUID, player_b_id: uuid.UUID,
    stake_amount: Decimal, game_type: str = "tictactoe",
) -> Match:
    """
    Creates the match row and locks both players' stakes.

    Randomly assigns X/O per the spec. If locking either player's
    stake fails (e.g. their balance changed between queueing and
    matching), the whole operation is rolled back and nobody is
    charged — safer to fail the match creation than charge only
    one player.
    """
    import random
    from app.services import checkers_service

    players = [player_a_id, player_b_id]
    random.shuffle(players)
    player_x_id, player_o_id = players[0], players[1]

    # Fee rule: 1 birr per 10 birr staked (10% of the stake), taken
    # from the pot when the match ends. e.g. 50 ETB stake -> 5 ETB fee.
    platform_fee = (stake_amount * Decimal("0.10")).quantize(Decimal("0.01"))

    initial_board = checkers_service.initial_board() if game_type == "checkers" else "_________"

    match = Match(
        game_type=game_type,
        stake_amount=stake_amount,
        platform_fee=platform_fee,
        player_x_id=player_x_id,
        player_o_id=player_o_id,
        current_turn="X",
        board=initial_board,
        status="active",
    )
    db.add(match)
    db.flush()  # get match.id without committing yet

    try:
        # Lock both stakes. Each lock_stake() call commits on its own
        # (that's how wallet_service works — one function = one atomic
        # step). That means if the SECOND lock fails, the first one is
        # already saved and a plain rollback won't undo it. So if step
        # two fails, we manually release step one's lock as a
        # "compensating transaction" before re-raising the error.
        wallet_service.lock_stake(db, player_x_id, stake_amount, match.id)
        try:
            wallet_service.lock_stake(db, player_o_id, stake_amount, match.id)
        except wallet_service.InsufficientBalanceError:
            # Undo player_x_id's lock so they aren't left stuck with
            # locked funds for a match that never actually started.
            wallet_service.release_single_stake(
                db,
                user_id=player_x_id,
                stake_amount=stake_amount,
                match_id=match.id,
                reason="opponent_insufficient_balance",
            )
            raise
    except wallet_service.InsufficientBalanceError:
        match.status = "voided"
        db.commit()
        raise

    db.commit()
    db.refresh(match)
    return match
