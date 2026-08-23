"""
routes/admin_dashboard.py

Powers the numbers shown on the admin panel's home screen.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.admin_auth import get_current_admin
from app.models.models import User, Match, Deposit, Withdrawal, Admin

router = APIRouter()


@router.get("/admin/dashboard")
def dashboard_stats(db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    total_users = db.query(func.count(User.internal_id)).scalar()
    active_users = db.query(func.count(User.internal_id)).filter(User.status == "active").scalar()

    completed_statuses = ["completed_win", "completed_draw", "completed_forfeit"]
    games_played = db.query(func.count(Match.id)).filter(Match.status.in_(completed_statuses)).scalar()
    active_matches = db.query(func.count(Match.id)).filter(Match.status == "active").scalar()

    total_stakes = db.query(func.coalesce(func.sum(Match.stake_amount * 2), 0)).filter(
        Match.status.in_(completed_statuses)
    ).scalar()

    # Fee only applies to win/forfeit matches, not draws (per your rule)
    fee_matches = db.query(func.count(Match.id)).filter(
        Match.status.in_(["completed_win", "completed_forfeit"])
    ).scalar()
    platform_fees = db.query(func.coalesce(func.sum(Match.platform_fee), 0)).filter(
        Match.status.in_(["completed_win", "completed_forfeit"])
    ).scalar()

    pending_deposits = db.query(func.count(Deposit.id)).filter(Deposit.status == "pending").scalar()
    pending_withdrawals = db.query(func.count(Withdrawal.id)).filter(Withdrawal.status == "pending").scalar()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "games_played": games_played,
        "active_matches": active_matches,
        "total_stakes": str(total_stakes),
        "platform_fees": str(platform_fees),
        "pending_deposits": pending_deposits,
        "pending_withdrawals": pending_withdrawals,
    }
