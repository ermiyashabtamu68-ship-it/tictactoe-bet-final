"""
routes/admin_users.py

Viewing registered users and suspending accounts (e.g. for
suspected cheating or abuse).
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.admin_auth import get_current_admin, require_role
from app.services.audit_service import log_admin_action
from app.models.models import User, Admin

router = APIRouter()


@router.get("/admin/users")
def list_users(
    search: str = None,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    query = db.query(User)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (User.full_name.ilike(like)) |
            (User.phone_number.ilike(like)) |
            (User.telegram_username.ilike(like))
        )
    users = query.order_by(User.registered_at.desc()).limit(100).all()

    return [
        {
            "internal_id": str(u.internal_id),
            "telegram_user_id": u.telegram_user_id,
            "full_name": u.full_name,
            "phone_number": u.phone_number,
            "status": u.status,
            "registered_at": u.registered_at.isoformat(),
            "wallet": {
                "available_balance": str(u.wallet.available_balance) if u.wallet else "0",
                "locked_balance": str(u.wallet.locked_balance) if u.wallet else "0",
            } if u.wallet else None,
        }
        for u in users
    ]


class SuspendUserRequest(BaseModel):
    reason: str


@router.post("/admin/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    payload: SuspendUserRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("support")),
):
    user = db.query(User).filter(User.internal_id == uuid.UUID(user_id)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    user.status = "suspended"
    log_admin_action(
        db, admin.id, action="user_suspended", target_type="user", target_id=user.internal_id,
        metadata={"reason": payload.reason}
    )
    db.commit()
    return {"status": "suspended", "user_id": user_id}


@router.post("/admin/users/{user_id}/reactivate")
def reactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_role("support")),
):
    user = db.query(User).filter(User.internal_id == uuid.UUID(user_id)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    user.status = "active"
    log_admin_action(
        db, admin.id, action="user_reactivated", target_type="user", target_id=user.internal_id
    )
    db.commit()
    return {"status": "active", "user_id": user_id}
