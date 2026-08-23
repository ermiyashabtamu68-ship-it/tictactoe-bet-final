"""
routes/deposits.py

Manual deposit flow. Users can only CREATE a pending deposit here.
Approving/rejecting is an ADMIN action (see routes/admin.py), never
something a user can trigger themselves — that's the whole point of
manual verification.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import DepositRequest
from app.services.user_service import get_user_or_404
from app.models.models import Deposit

router = APIRouter()


@router.post("/deposits")
def create_deposit(payload: DepositRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, payload.telegram_user_id)

    if payload.payment_method not in ("telebirr", "nib_bank"):
        raise HTTPException(status_code=400, detail="Invalid payment method.")

    deposit = Deposit(
        user_id=user.internal_id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        reference_number=payload.reference_number,
        screenshot_file_id=payload.screenshot_file_id,
        status="pending",
    )
    db.add(deposit)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This reference number is already pending or was already approved."
        )
    db.refresh(deposit)

    return {
        "deposit_id": str(deposit.id),
        "status": deposit.status,
        "message": "Deposit submitted. An admin will review it shortly. Your balance will update once approved.",
    }
