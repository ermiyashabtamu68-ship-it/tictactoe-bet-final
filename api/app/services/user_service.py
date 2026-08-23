"""
services/user_service.py

Handles registration and lookup by Telegram ID. Every route that
receives a telegram_user_id needs to translate it into our internal
UUID before doing anything else — this file is where that happens.
"""

import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from app.models.models import User, Wallet


def get_user_by_username(db: Session, username: str) -> User | None:
    """
    Looks up a user by their Telegram @username (case-insensitive,
    with or without a leading @). Used for the "challenge a friend
    by username" flow. Returns None if nobody with that username
    has registered with the bot.
    """
    cleaned = username.strip().lstrip("@").lower()
    if not cleaned:
        return None
    return (
        db.query(User)
        .filter(func.lower(User.telegram_username) == cleaned)
        .first()
    )


def get_or_create_user(
    db: Session,
    telegram_user_id: int,
    telegram_username: str | None,
    full_name: str | None = None,
    phone_number: str | None = None,
) -> User:
    """
    Registration is "get or create". On a brand-new user, full_name
    and phone_number are required (the bot collects them before
    calling this). On a returning user, they're ignored — we don't
    silently overwrite what they registered with.
    """
    user = db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    if user:
        if telegram_username and user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
            db.commit()
        return user

    if not full_name or not phone_number:
        raise HTTPException(
            status_code=400,
            detail="full_name and phone_number are required to register."
        )

    user = User(
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        full_name=full_name.strip(),
        phone_number=phone_number.strip(),
    )
    db.add(user)
    db.flush()  # so user.internal_id is available for the wallet below

    wallet = Wallet(user_id=user.internal_id)
    db.add(wallet)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This phone number is already registered to another account."
        )
    db.refresh(user)
    return user


def get_user_or_404(db: Session, telegram_user_id: int) -> User:
    user = db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not registered. Send /start first.")
    return user
