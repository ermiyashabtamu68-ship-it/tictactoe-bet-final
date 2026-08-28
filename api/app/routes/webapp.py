"""
routes/webapp.py

Every endpoint the full Mini App calls. Unlike the bot's endpoints
(which trust a plain telegram_user_id in the request body — safe
enough because the bot itself is the one sending it), everything
here identifies the player from Telegram's SIGNED initData header
instead, since a webpage's requests could otherwise be spoofed.

This mostly wires the Mini App to the exact same services the bot
uses (wallet_service, matchmaking_service, friend_service, etc.) so
there's one source of truth for the actual game/money logic —
this file is just a different front door to it.
"""

import os
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.core.telegram_auth import verify_init_data, InvalidInitDataError
from app.services.user_service import get_or_create_user, get_user_or_404
from app.services import wallet_service, matchmaking_service, friend_service
from app.models.models import User, Deposit, Withdrawal, Match

router = APIRouter(prefix="/webapp")

UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _webapp_identity(x_telegram_init_data: str = Header(None)) -> dict:
    try:
        return verify_init_data(x_telegram_init_data)
    except InvalidInitDataError as e:
        raise HTTPException(status_code=401, detail=str(e))


def _webapp_user(db: Session, x_telegram_init_data: str = Header(None)) -> User:
    tg_user = _webapp_identity(x_telegram_init_data)
    return get_user_or_404(db, tg_user["id"])


def _wallet_dict(wallet) -> dict:
    return {
        "available_balance": str(wallet.available_balance),
        "locked_balance": str(wallet.locked_balance),
        "total_winnings": str(wallet.total_winnings),
        "total_games": wallet.total_games,
        "total_deposits": str(wallet.total_deposits),
        "total_withdrawals": str(wallet.total_withdrawals),
    }


# ---------------- Identity / registration ----------------

@router.get("/me")
def get_me(db: Session = Depends(get_db), x_telegram_init_data: str = Header(None)):
    """
    First call the app makes on open. If this Telegram account has
    never registered, tells the app to show the registration form
    instead of the dashboard.
    """
    tg_user = _webapp_identity(x_telegram_init_data)
    user = db.query(User).filter(User.telegram_user_id == tg_user["id"]).first()

    if user is None:
        return {
            "registered": False,
            "telegram_username": tg_user.get("username"),
            "telegram_first_name": tg_user.get("first_name"),
        }

    return {
        "registered": True,
        "telegram_user_id": user.telegram_user_id,
        "telegram_username": user.telegram_username,
        "full_name": user.full_name,
        "wallet": _wallet_dict(user.wallet),
    }


@router.post("/register")
def register(
    full_name: str = Form(...),
    phone_number: str = Form(...),
    db: Session = Depends(get_db),
    x_telegram_init_data: str = Header(None),
):
    tg_user = _webapp_identity(x_telegram_init_data)
    user = get_or_create_user(
        db, tg_user["id"], tg_user.get("username"),
        full_name=full_name, phone_number=phone_number,
    )
    return {"registered": True, "telegram_user_id": user.telegram_user_id}


# ---------------- Wallet / history ----------------

@router.get("/wallet")
def get_wallet(db: Session = Depends(get_db), x_telegram_init_data: str = Header(None)):
    user = _webapp_user(db, x_telegram_init_data)
    return _wallet_dict(user.wallet)


@router.get("/history")
def get_history(db: Session = Depends(get_db), x_telegram_init_data: str = Header(None)):
    user = _webapp_user(db, x_telegram_init_data)
    matches = (
        db.query(Match)
        .filter(
            (Match.player_x_id == user.internal_id) | (Match.player_o_id == user.internal_id),
            Match.status != "active",
        )
        .order_by(Match.settled_at.desc())
        .limit(30)
        .all()
    )
    return {
        "matches": [
            {
                "match_id": str(m.id),
                "game_type": m.game_type,
                "stake_amount": str(m.stake_amount),
                "status": m.status,
                "you_won": (m.winner_id == user.internal_id) if m.winner_id else None,
                "payout_amount": str(m.payout_amount) if m.payout_amount is not None else None,
                "settled_at": m.settled_at.isoformat() if m.settled_at else None,
            }
            for m in matches
        ]
    }


# ---------------- Deposits / withdrawals ----------------

@router.post("/deposits")
async def create_deposit(
    amount: str = Form(...),
    payment_method: str = Form(...),
    reference_number: str = Form(...),
    screenshot: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_telegram_init_data: str = Header(None),
):
    user = _webapp_user(db, x_telegram_init_data)

    if payment_method not in ("telebirr", "nib_bank"):
        raise HTTPException(status_code=400, detail="Invalid payment method.")
    try:
        amount_dec = Decimal(amount)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Invalid amount.")
    if amount_dec < Decimal("25"):
        raise HTTPException(status_code=400, detail="Minimum deposit is 25 ETB.")

    ext = os.path.splitext(screenshot.filename or "")[1] or ".jpg"
    saved_name = f"{uuid.uuid4()}{ext}"
    with open(os.path.join(UPLOAD_DIR, saved_name), "wb") as f:
        f.write(await screenshot.read())

    deposit = Deposit(
        user_id=user.internal_id,
        amount=amount_dec,
        payment_method=payment_method,
        reference_number=reference_number,
        screenshot_file_id=f"webapp:{saved_name}",
        status="pending",
    )
    db.add(deposit)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="This reference number is already pending or was already approved.")

    return {"deposit_id": str(deposit.id), "status": "pending"}


@router.post("/withdrawals")
def create_withdrawal(
    amount: str = Form(...),
    payment_method: str = Form(...),
    payment_details: str = Form(...),
    db: Session = Depends(get_db),
    x_telegram_init_data: str = Header(None),
):
    user = _webapp_user(db, x_telegram_init_data)

    if payment_method not in ("telebirr", "nib_bank"):
        raise HTTPException(status_code=400, detail="Invalid payment method.")
    try:
        amount_dec = Decimal(amount)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Invalid amount.")
    if amount_dec < Decimal("25"):
        raise HTTPException(status_code=400, detail="Minimum withdrawal is 25 ETB.")

    withdrawal = Withdrawal(
        user_id=user.internal_id, amount=amount_dec,
        payment_method=payment_method, payment_details=payment_details, status="pending",
    )
    db.add(withdrawal)
    db.flush()

    try:
        wallet_service.lock_withdrawal_amount(db, user_id=user.internal_id, amount=amount_dec, withdrawal_id=withdrawal.id)
    except wallet_service.InsufficientBalanceError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Insufficient available balance.")

    db.commit()
    return {"withdrawal_id": str(withdrawal.id), "status": "pending"}


# ---------------- Matchmaking ----------------

@router.get("/matchmaking/open")
def list_open_matches(db: Session = Depends(get_db), redis_client=Depends(get_redis), x_telegram_init_data: str = Header(None)):
    user = _webapp_user(db, x_telegram_init_data)
    return {"open_matches": matchmaking_service.list_open_matches(redis_client, db, user.internal_id)}


@router.post("/matchmaking/join-open")
def join_open_match(
    opponent_id: str = Form(...), stake_amount: str = Form(...), game_type: str = Form("tictactoe"),
    db: Session = Depends(get_db), redis_client=Depends(get_redis),
    x_telegram_init_data: str = Header(None),
):
    user = _webapp_user(db, x_telegram_init_data)
    try:
        result = matchmaking_service.join_open_match(
            redis_client, db, user.internal_id, uuid.UUID(opponent_id), Decimal(stake_amount), game_type,
        )
    except matchmaking_service.OpponentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except matchmaking_service.InsufficientBalanceForStakeError:
        raise HTTPException(status_code=400, detail="Insufficient balance for this stake.")
    return result


@router.post("/matchmaking/join")
def join_queue(
    stake_amount: str = Form(...), game_type: str = Form("tictactoe"),
    db: Session = Depends(get_db), redis_client=Depends(get_redis),
    x_telegram_init_data: str = Header(None),
):
    user = _webapp_user(db, x_telegram_init_data)
    try:
        result = matchmaking_service.join_queue(
            redis_client, db, user_id=user.internal_id,
            stake_amount=Decimal(stake_amount), game_type=game_type,
        )
    except matchmaking_service.InsufficientBalanceForStakeError:
        raise HTTPException(status_code=400, detail="Insufficient balance for this stake.")
    return result


@router.post("/matchmaking/leave")
def leave_queue(
    stake_amount: str = Form(...), game_type: str = Form("tictactoe"),
    db: Session = Depends(get_db), redis_client=Depends(get_redis),
    x_telegram_init_data: str = Header(None),
):
    user = _webapp_user(db, x_telegram_init_data)
    removed = matchmaking_service.leave_queue(redis_client, user.internal_id, Decimal(stake_amount), game_type)
    return {"removed": removed}


@router.get("/matchmaking/status")
def check_status(db: Session = Depends(get_db), x_telegram_init_data: str = Header(None)):
    user = _webapp_user(db, x_telegram_init_data)
    match = matchmaking_service.check_if_matched(db, user.internal_id)
    if match is None:
        return {"status": "waiting"}
    return {"status": "matched", "match_id": str(match.id)}


# ---------------- Friends ----------------

@router.get("/friends")
def get_friends(db: Session = Depends(get_db), x_telegram_init_data: str = Header(None)):
    user = _webapp_user(db, x_telegram_init_data)
    friends = friend_service.list_friends(db, user)
    pending = friend_service.list_pending_requests(db, user)
    return {
        "friends": [
            {"internal_id": str(f.internal_id), "telegram_username": f.telegram_username, "full_name": f.full_name}
            for f in friends
        ],
        "pending_requests": [
            {"request_id": str(p.id), "requester_id": str(p.requester_id)}
            for p in pending
        ],
    }


@router.post("/friends/request")
def send_friend_request(
    friend_username: str = Form(...),
    db: Session = Depends(get_db), x_telegram_init_data: str = Header(None),
):
    user = _webapp_user(db, x_telegram_init_data)
    try:
        friendship = friend_service.send_request(db, user, friend_username)
    except friend_service.FriendNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except friend_service.CannotFriendSelfError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except friend_service.AlreadyFriendsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"request_id": str(friendship.id)}


@router.post("/friends/respond")
def respond_friend_request(
    request_id: str = Form(...), accept: bool = Form(...),
    db: Session = Depends(get_db), x_telegram_init_data: str = Header(None),
):
    user = _webapp_user(db, x_telegram_init_data)
    try:
        friendship = friend_service.respond_request(db, user, request_id, accept)
    except friend_service.RequestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": friendship.status}


@router.post("/friends/invite")
async def invite_friend(
    friend_id: str = Form(...), stake_amount: str = Form(...), game_type: str = Form("tictactoe"),
    db: Session = Depends(get_db), redis_client=Depends(get_redis),
    x_telegram_init_data: str = Header(None),
):
    user = _webapp_user(db, x_telegram_init_data)
    try:
        result = await friend_service.invite_friend(redis_client, db, user, friend_id, Decimal(stake_amount), game_type)
    except friend_service.FriendNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except friend_service.NotFriendsError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except matchmaking_service.InsufficientBalanceForStakeError:
        raise HTTPException(status_code=400, detail="Insufficient balance for this stake.")
    return result
