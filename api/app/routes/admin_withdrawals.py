"""
routes/admin_withdrawals.py

Where finance marks a withdrawal Paid (after manually sending the
money via Telebirr/bank) or Rejected (money is returned to the
user's available balance automatically).
"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.admin_auth import require_role, get_current_admin
from app.services import wallet_service
from app.services.audit_service import log_admin_action
from app.models.models import Withdrawal, Admin

router = APIRouter()


@router.get("/admin/withdrawals")
def list_withdrawals(
    status: str = "pending",
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    withdrawals = (
        db.query(Withdrawal)
        .filter(Withdrawal.status == status)
        .order_by(Withdrawal.created_at.asc())
        .all()
    )
    return [
        {
            "id": str(w.id),
            "user_id": str(w.user_id),
            "amount": str(w.amount),
            "payment_method": w.payment_method,
            "payment_details": w.payment_details,
            "status": w.status,
            "created_at": w.created_at.isoformat(),
        }
        for w in withdrawals
    ]


class RejectWithdrawalRequest(BaseModel):
    reason: str


@router.post("/admin/withdrawals/{withdrawal_id}/mark_paid")
def mark_withdrawal_paid(
    withdrawal_id: str,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("finance")),
):
    withdrawal = db.query(Withdrawal).filter(Withdrawal.id == uuid.UUID(withdrawal_id)).first()
    if withdrawal is None:
        raise HTTPException(status_code=404, detail="Withdrawal not found.")
    if withdrawal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Withdrawal already {withdrawal.status}.")

    withdrawal.status = "paid"
    withdrawal.reviewed_by_admin_id = admin.id
    withdrawal.reviewed_at = datetime.now(timezone.utc)

    log_admin_action(
        db, admin.id, action="withdrawal_paid", target_type="withdrawal", target_id=withdrawal.id,
        metadata={"amount": str(withdrawal.amount)}
    )

    wallet_service.finalize_withdrawal_paid(
        db, user_id=withdrawal.user_id, amount=withdrawal.amount, withdrawal_id=withdrawal.id
    )

    return {"status": "paid", "withdrawal_id": withdrawal_id}


@router.post("/admin/withdrawals/{withdrawal_id}/reject")
def reject_withdrawal(
    withdrawal_id: str,
    payload: RejectWithdrawalRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("finance")),
):
    withdrawal = db.query(Withdrawal).filter(Withdrawal.id == uuid.UUID(withdrawal_id)).first()
    if withdrawal is None:
        raise HTTPException(status_code=404, detail="Withdrawal not found.")
    if withdrawal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Withdrawal already {withdrawal.status}.")

    withdrawal.status = "rejected"
    withdrawal.reviewed_by_admin_id = admin.id
    withdrawal.rejection_reason = payload.reason
    withdrawal.reviewed_at = datetime.now(timezone.utc)

    log_admin_action(
        db, admin.id, action="withdrawal_rejected", target_type="withdrawal", target_id=withdrawal.id,
        metadata={"reason": payload.reason}
    )

    wallet_service.reject_withdrawal(
        db, user_id=withdrawal.user_id, amount=withdrawal.amount, withdrawal_id=withdrawal.id
    )

    return {"status": "rejected", "withdrawal_id": withdrawal_id}
