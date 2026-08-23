"""
routes/matchmaking.py

Joining/leaving the matchmaking queue, and checking match status
while waiting.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.schemas import JoinQueueRequest
from app.services.user_service import get_user_or_404
from app.services import matchmaking_service

router = APIRouter()


@router.post("/matchmaking/join")
def join_queue(payload: JoinQueueRequest, db: Session = Depends(get_db), redis_client=Depends(get_redis)):
    user = get_user_or_404(db, payload.telegram_user_id)

    try:
        result = matchmaking_service.join_queue(
            redis_client, db, user_id=user.internal_id,
            stake_amount=payload.stake_amount, game_type=payload.game_type,
        )
    except matchmaking_service.InsufficientBalanceForStakeError:
        raise HTTPException(status_code=400, detail="Insufficient balance for this stake.")

    return result


@router.post("/matchmaking/leave")
def leave_queue(payload: JoinQueueRequest, db: Session = Depends(get_db), redis_client=Depends(get_redis)):
    user = get_user_or_404(db, payload.telegram_user_id)
    removed = matchmaking_service.leave_queue(redis_client, user.internal_id, payload.stake_amount, payload.game_type)
    return {"removed": removed}


@router.get("/matchmaking/status/{telegram_user_id}")
def check_status(telegram_user_id: int, db: Session = Depends(get_db)):
    """
    Lightweight check: has this player been matched into an active
    match yet? Used by the bot's polling loop while a player waits,
    instead of re-calling join_queue (which has side effects on the
    Redis queue).
    """
    user = get_user_or_404(db, telegram_user_id)
    match = matchmaking_service.check_if_matched(db, user.internal_id)
    if match is None:
        return {"status": "waiting"}
    return {"status": "matched", "match_id": str(match.id)}
