"""
routes/challenges.py

Friend-vs-friend matches: Player A types Player B's @username and
challenges them directly for a chosen stake, instead of waiting in
the random matchmaking queue. Player B gets an Accept/Decline prompt.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.schemas import CreateChallengeRequest, RespondChallengeRequest
from app.services.user_service import get_user_or_404
from app.services import matchmaking_service

router = APIRouter()


@router.post("/challenges")
def create_challenge(payload: CreateChallengeRequest, db: Session = Depends(get_db), redis_client=Depends(get_redis)):
    user = get_user_or_404(db, payload.telegram_user_id)

    try:
        result = matchmaking_service.create_challenge(
            redis_client, db, user, payload.opponent_username, payload.stake_amount
        )
    except matchmaking_service.OpponentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except matchmaking_service.CannotChallengeSelfError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except matchmaking_service.InsufficientBalanceForStakeError:
        raise HTTPException(status_code=400, detail="Insufficient balance for this stake.")

    return result


@router.post("/challenges/respond")
def respond_challenge(payload: RespondChallengeRequest, db: Session = Depends(get_db), redis_client=Depends(get_redis)):
    user = get_user_or_404(db, payload.telegram_user_id)

    try:
        result = matchmaking_service.respond_challenge(redis_client, db, user, payload.accept)
    except matchmaking_service.ChallengeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except matchmaking_service.InsufficientBalanceForStakeError:
        raise HTTPException(status_code=400, detail="Insufficient balance for this stake.")

    return result
