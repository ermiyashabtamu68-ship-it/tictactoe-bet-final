"""
routes/withdrawals.py

Manual withdrawal flow. Creating a request immediately LOCKS the
requested amount (via wallet_service.lock_withdrawal_amount) so the
user can't spend it on a match while the admin is processing it.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import WithdrawalRequest
from app.services.user_service import get_user_or_404
from app.services import wallet_service
from app.models.models import Withdrawal

router = APIRouter()


@router.post("/withdrawals")
def create_withdrawal(payload: WithdrawalRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, payload.telegram_user_id)

    if payload.payment_method not in ("telebirr", "nib_bank"):
        raise HTTPException(status_code=400, detail="Invalid payment method.")

    withdrawal = Withdrawal(
        user_id=user.internal_id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        payment_details=payload.payment_details,
        status="pending",
    )
    db.add(withdrawal)
    db.flush()  # get withdrawal.id before locking funds

    try:
        wallet_service.lock_withdrawal_amount(
            db, user_id=user.internal_id, amount=payload.amount, withdrawal_id=withdrawal.id
        )
    except wallet_service.InsufficientBalanceError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Insufficient available balance.")

    db.commit()
    db.refresh(withdrawal)

    return {
        "withdrawal_id": str(withdrawal.id),
        "status": withdrawal.status,
        "message": "Withdrawal requested. An admin will process payment shortly.",
    }
