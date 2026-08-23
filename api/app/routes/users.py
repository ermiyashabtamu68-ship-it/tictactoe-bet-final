"""
routes/users.py

Registration, and reading a user's wallet/history.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import RegisterUserRequest
from app.services.user_service import get_or_create_user, get_user_or_404
from app.models.models import Match

router = APIRouter()


@router.post("/users/register")
def register_user(payload: RegisterUserRequest, db: Session = Depends(get_db)):
    user = get_or_create_user(
        db,
        payload.telegram_user_id,
        payload.telegram_username,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
    )
    return {
        "internal_id": str(user.internal_id),
        "telegram_user_id": user.telegram_user_id,
        "status": user.status,
    }


@router.get("/wallet/{telegram_user_id}")
def get_wallet(telegram_user_id: int, db: Session = Depends(get_db)):
    user = get_user_or_404(db, telegram_user_id)
    wallet = user.wallet
    return {
        "available_balance": str(wallet.available_balance),
        "locked_balance": str(wallet.locked_balance),
        "total_winnings": str(wallet.total_winnings),
        "total_games": wallet.total_games,
        "total_deposits": str(wallet.total_deposits),
        "total_withdrawals": str(wallet.total_withdrawals),
    }


@router.get("/users/{telegram_user_id}/history")
def get_history(telegram_user_id: int, db: Session = Depends(get_db)):
    user = get_user_or_404(db, telegram_user_id)

    matches = (
        db.query(Match)
        .filter(
            (Match.player_x_id == user.internal_id) | (Match.player_o_id == user.internal_id),
            Match.status != "active",
        )
        .order_by(Match.settled_at.desc())
        .limit(20)
        .all()
    )

    results = []
    for m in matches:
        you_won = m.winner_id == user.internal_id if m.winner_id else None
        results.append({
            "match_id": str(m.id),
            "stake_amount": str(m.stake_amount),
            "status": m.status,
            "you_won": you_won,
            "payout_amount": str(m.payout_amount) if m.payout_amount is not None else None,
            "settled_at": m.settled_at.isoformat() if m.settled_at else None,
        })

    return {"matches": results}
