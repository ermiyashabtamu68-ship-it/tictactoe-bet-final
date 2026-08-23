"""
routes/admin_deposits.py

Where Yafet (finance) approves or rejects pending deposits. This is
the ONLY place a wallet gets credited from a deposit — never
automatic, always a human decision after checking the real
Telebirr/bank account.
"""

import os
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.admin_auth import require_role, get_current_admin
from app.services import wallet_service
from app.services.audit_service import log_admin_action
from app.models.models import Deposit, Admin

router = APIRouter()


@router.get("/admin/deposits/{deposit_id}/screenshot")
async def get_deposit_screenshot(
    deposit_id: str,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    """
    Streams the actual screenshot image back to the admin panel, by
    asking Telegram's servers for it using the bot token. We never
    store the image ourselves — we just fetch it fresh from Telegram
    each time using the file_id we saved.
    """
    deposit = db.query(Deposit).filter(Deposit.id == uuid.UUID(deposit_id)).first()
    if deposit is None:
        raise HTTPException(status_code=404, detail="Deposit not found.")

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Server is not configured with BOT_TOKEN.")

    async with httpx.AsyncClient(timeout=10) as client:
        file_info_resp = await client.get(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            params={"file_id": deposit.screenshot_file_id},
        )
        file_info = file_info_resp.json()
        if not file_info.get("ok"):
            raise HTTPException(status_code=502, detail="Could not fetch screenshot from Telegram.")

        file_path = file_info["result"]["file_path"]
        image_resp = await client.get(
            f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        )

    return StreamingResponse(iter([image_resp.content]), media_type="image/jpeg")


@router.get("/admin/deposits")
def list_deposits(
    status: str = "pending",
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    deposits = (
        db.query(Deposit)
        .filter(Deposit.status == status)
        .order_by(Deposit.created_at.asc())
        .all()
    )
    return [
        {
            "id": str(d.id),
            "user_id": str(d.user_id),
            "amount": str(d.amount),
            "payment_method": d.payment_method,
            "reference_number": d.reference_number,
            "screenshot_file_id": d.screenshot_file_id,
            "status": d.status,
            "created_at": d.created_at.isoformat(),
        }
        for d in deposits
    ]


class RejectDepositRequest(BaseModel):
    reason: str


@router.post("/admin/deposits/{deposit_id}/approve")
def approve_deposit(
    deposit_id: str,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("finance")),
):
    deposit = db.query(Deposit).filter(Deposit.id == uuid.UUID(deposit_id)).first()
    if deposit is None:
        raise HTTPException(status_code=404, detail="Deposit not found.")
    if deposit.status != "pending":
        raise HTTPException(status_code=409, detail=f"Deposit already {deposit.status}.")

    deposit.status = "approved"
    deposit.reviewed_by_admin_id = admin.id
    from datetime import datetime, timezone
    deposit.reviewed_at = datetime.now(timezone.utc)

    log_admin_action(
        db, admin.id, action="deposit_approved", target_type="deposit", target_id=deposit.id,
        metadata={"amount": str(deposit.amount)}
    )

    # credit_deposit() commits the whole session, which includes the
    # deposit status change and audit log row above, so all three
    # succeed or fail together.
    wallet_service.credit_deposit(db, user_id=deposit.user_id, amount=deposit.amount, deposit_id=deposit.id)

    return {"status": "approved", "deposit_id": deposit_id}


@router.post("/admin/deposits/{deposit_id}/reject")
def reject_deposit(
    deposit_id: str,
    payload: RejectDepositRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("finance")),
):
    deposit = db.query(Deposit).filter(Deposit.id == uuid.UUID(deposit_id)).first()
    if deposit is None:
        raise HTTPException(status_code=404, detail="Deposit not found.")
    if deposit.status != "pending":
        raise HTTPException(status_code=409, detail=f"Deposit already {deposit.status}.")

    deposit.status = "rejected"
    deposit.reviewed_by_admin_id = admin.id
    deposit.rejection_reason = payload.reason
    from datetime import datetime, timezone
    deposit.reviewed_at = datetime.now(timezone.utc)

    log_admin_action(
        db, admin.id, action="deposit_rejected", target_type="deposit", target_id=deposit.id,
        metadata={"reason": payload.reason}
    )
    db.commit()

    return {"status": "rejected", "deposit_id": deposit_id}
