"""
routes/admin_auth.py

Admin login. This is the entry point Yafet, Nahom, and you use to
get a token, which then has to be sent with every other admin
request (see core/admin_auth.py's get_current_admin).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.admin_auth import verify_password, create_admin_token
from app.core.rate_limit import limiter
from app.models.models import Admin

router = APIRouter()


class AdminLoginRequest(BaseModel):
    username: str
    password: str


@router.post("/admin/login")
@limiter.limit("5/minute")  # blocks rapid password-guessing attempts
def admin_login(request: Request, payload: AdminLoginRequest, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == payload.username).first()

    # Deliberately vague error message — doesn't reveal whether the
    # username exists, which makes it harder for someone to guess
    # valid admin usernames.
    if admin is None or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = create_admin_token(admin.id, admin.role)
    return {
        "token": token,
        "role": admin.role,
        "username": admin.username,
    }
