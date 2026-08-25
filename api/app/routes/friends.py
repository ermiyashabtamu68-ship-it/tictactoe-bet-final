"""
routes/friends.py

Friend requests: send one, accept/decline one, list your accepted
friends, and invite an accepted friend to a match directly (no need
to type their username again).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.schemas import FriendRequestCreate, FriendRequestRespond, FriendInviteRequest
from app.services.user_service import get_user_or_404
from app.services import friend_service, matchmaking_service

router = APIRouter()


@router.post("/friends/request")
def send_friend_request(payload: FriendRequestCreate, db: Session = Depends(get_db)):
    user = get_user_or_404(db, payload.telegram_user_id)
    try:
        friendship = friend_service.send_request(db, user, payload.friend_username)
    except friend_service.FriendNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except friend_service.CannotFriendSelfError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except friend_service.AlreadyFriendsError as e:
        raise HTTPException(status_code=409, detail=str(e))

    addressee = db.query(friend_service.User).filter(
        friend_service.User.internal_id == friendship.addressee_id
    ).first()

    return {
        "request_id": str(friendship.id),
        "addressee_telegram_id": addressee.telegram_user_id,
        "addressee_username": addressee.telegram_username,
    }


@router.post("/friends/respond")
def respond_friend_request(payload: FriendRequestRespond, db: Session = Depends(get_db)):
    user = get_user_or_404(db, payload.telegram_user_id)
    try:
        friendship = friend_service.respond_request(db, user, payload.request_id, payload.accept)
    except friend_service.RequestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    requester = db.query(friend_service.User).filter(
        friend_service.User.internal_id == friendship.requester_id
    ).first()

    return {
        "status": friendship.status,
        "requester_telegram_id": requester.telegram_user_id,
        "requester_username": requester.telegram_username,
    }


@router.get("/friends/{telegram_user_id}")
def get_friends(telegram_user_id: int, db: Session = Depends(get_db)):
    user = get_user_or_404(db, telegram_user_id)
    friends = friend_service.list_friends(db, user)
    return {
        "friends": [
            {
                "internal_id": str(f.internal_id),
                "telegram_username": f.telegram_username,
                "full_name": f.full_name,
            }
            for f in friends
        ]
    }


@router.get("/friends/{telegram_user_id}/requests")
def get_pending_requests(telegram_user_id: int, db: Session = Depends(get_db)):
    user = get_user_or_404(db, telegram_user_id)
    pending = friend_service.list_pending_requests(db, user)
    result = []
    for p in pending:
        requester = db.query(friend_service.User).filter(
            friend_service.User.internal_id == p.requester_id
        ).first()
        result.append({
            "request_id": str(p.id),
            "requester_telegram_id": requester.telegram_user_id,
            "requester_username": requester.telegram_username,
        })
    return {"requests": result}


@router.post("/friends/invite")
def invite_friend(payload: FriendInviteRequest, db: Session = Depends(get_db), redis_client=Depends(get_redis)):
    user = get_user_or_404(db, payload.telegram_user_id)
    try:
        result = friend_service.invite_friend(
            redis_client, db, user, payload.friend_id, payload.stake_amount, payload.game_type,
        )
    except friend_service.FriendNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except friend_service.NotFriendsError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except matchmaking_service.InsufficientBalanceForStakeError:
        raise HTTPException(status_code=400, detail="Insufficient balance for this stake.")

    return result
