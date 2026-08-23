"""
core/admin_auth.py

Handles admin login checks. Kept separate from user auth because
admins are a completely different kind of account (staff, not
players) with their own password and role.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Admin

JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "CHANGE_ME_IN_ENV")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 12


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), password_hash.encode())


def create_admin_token(admin_id: uuid.UUID, role: str) -> str:
    payload = {
        "admin_id": str(admin_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_admin(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> Admin:
    """
    Reads the "Authorization: Bearer <token>" header the admin panel
    sends with every request, checks it's valid, and returns the
    admin record. Every admin-only route depends on this function —
    if the token is missing or invalid, the request is rejected
    before any admin logic runs.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")

    admin = db.query(Admin).filter(Admin.id == uuid.UUID(payload["admin_id"])).first()
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=401, detail="Admin account not found or disabled.")

    return admin


def require_role(*allowed_roles: str):
    """
    Use as a dependency to restrict a route to specific roles, e.g.
    only 'finance' or 'super_admin' can approve deposits.
    Example: Depends(require_role("finance", "super_admin"))
    """
    def checker(admin: Admin = Depends(get_current_admin)) -> Admin:
        if admin.role not in allowed_roles and admin.role != "super_admin":
            raise HTTPException(status_code=403, detail="You don't have permission for this action.")
        return admin
    return checker
