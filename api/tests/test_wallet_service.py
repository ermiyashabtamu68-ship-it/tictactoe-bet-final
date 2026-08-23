"""
test_wallet_service.py

Tests the money-handling logic in wallet_service.py — the most
important file in the whole project, since it controls every
balance change.

IMPORTANT: these tests need a REAL PostgreSQL database (not just
Python) because our models use PostgreSQL-specific features (UUID
columns, JSONB). Run them like this, from your server after Docker
is set up:

    docker compose exec api pytest tests/test_wallet_service.py -v

Each test creates its own throwaway user/wallet and cleans up after
itself, so tests don't interfere with each other or with real data.
"""

import sys
import os
import uuid
from decimal import Decimal
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.models.models import User, Wallet
from app.services import wallet_service


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()  # undo anything the test did, so the DB stays clean
    session.close()


@pytest.fixture
def test_user(db):
    """Creates a throwaway user + wallet for one test, deleted after."""
    user = User(
        telegram_user_id=900000000 + uuid.uuid4().int % 100000,
        full_name="Test User",
        phone_number=f"09{uuid.uuid4().int % 100000000}",
    )
    db.add(user)
    db.flush()
    wallet = Wallet(user_id=user.internal_id)
    db.add(wallet)
    db.commit()
    yield user
    db.delete(wallet)
    db.delete(user)
    db.commit()


def make_second_user(db):
    user = User(
        telegram_user_id=800000000 + uuid.uuid4().int % 100000,
        full_name="Test Opponent",
        phone_number=f"08{uuid.uuid4().int % 100000000}",
    )
    db.add(user)
    db.flush()
    wallet = Wallet(user_id=user.internal_id)
    db.add(wallet)
    db.commit()
    return user


# ------------------------------------------------------------------
# Deposits
# ------------------------------------------------------------------

def test_credit_deposit_increases_available_balance(db, test_user):
    deposit_id = uuid.uuid4()
    wallet_service.credit_deposit(db, test_user.internal_id, Decimal("50"), deposit_id)

    wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
    assert wallet.available_balance == Decimal("50")
    assert wallet.total_deposits == Decimal("50")


def test_credit_deposit_same_id_twice_raises_error(db, test_user):
    deposit_id = uuid.uuid4()
    wallet_service.credit_deposit(db, test_user.internal_id, Decimal("50"), deposit_id)

    with pytest.raises(wallet_service.DuplicateTransactionError):
        wallet_service.credit_deposit(db, test_user.internal_id, Decimal("50"), deposit_id)

    # Balance should still only reflect ONE deposit, not two
    wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
    assert wallet.available_balance == Decimal("50")


# ------------------------------------------------------------------
# Stakes
# ------------------------------------------------------------------

def test_lock_stake_moves_money_to_locked(db, test_user):
    wallet_service.credit_deposit(db, test_user.internal_id, Decimal("100"), uuid.uuid4())

    match_id = uuid.uuid4()
    wallet_service.lock_stake(db, test_user.internal_id, Decimal("50"), match_id)

    wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
    assert wallet.available_balance == Decimal("50")
    assert wallet.locked_balance == Decimal("50")


def test_lock_stake_fails_with_insufficient_balance(db, test_user):
    # User has 0 balance, tries to stake 50
    with pytest.raises(wallet_service.InsufficientBalanceError):
        wallet_service.lock_stake(db, test_user.internal_id, Decimal("50"), uuid.uuid4())


# ------------------------------------------------------------------
# Match settlement — the most important tests in this file
# ------------------------------------------------------------------

def test_settle_match_win_pays_correct_amount(db, test_user):
    opponent = make_second_user(db)
    try:
        wallet_service.credit_deposit(db, test_user.internal_id, Decimal("50"), uuid.uuid4())
        wallet_service.credit_deposit(db, opponent.internal_id, Decimal("50"), uuid.uuid4())

        match_id = uuid.uuid4()
        wallet_service.lock_stake(db, test_user.internal_id, Decimal("50"), match_id)
        wallet_service.lock_stake(db, opponent.internal_id, Decimal("50"), match_id)

        result = wallet_service.settle_match_win(
            db,
            winner_id=test_user.internal_id,
            loser_id=opponent.internal_id,
            stake_amount=Decimal("50"),
            platform_fee=Decimal("5"),
            match_id=match_id,
        )

        # Per the spec's example: 50 + 50 - 5 fee = 95 ETB payout
        assert result["payout"] == Decimal("95")

        winner_wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
        loser_wallet = db.query(Wallet).filter(Wallet.user_id == opponent.internal_id).first()

        assert winner_wallet.available_balance == Decimal("95")  # 0 available + 95 payout
        assert winner_wallet.locked_balance == Decimal("0")
        assert loser_wallet.available_balance == Decimal("0")
        assert loser_wallet.locked_balance == Decimal("0")  # their 50 stake is gone
    finally:
        db.delete(opponent.wallet)
        db.delete(opponent)
        db.commit()


def test_settle_match_win_cannot_be_applied_twice(db, test_user):
    """
    This is the critical anti-cheat test: a match must be impossible
    to settle twice. Calling settle_match_win a second time with the
    same match_id must be rejected by the idempotency key, not
    silently pay out again.
    """
    opponent = make_second_user(db)
    try:
        wallet_service.credit_deposit(db, test_user.internal_id, Decimal("50"), uuid.uuid4())
        wallet_service.credit_deposit(db, opponent.internal_id, Decimal("50"), uuid.uuid4())

        match_id = uuid.uuid4()
        wallet_service.lock_stake(db, test_user.internal_id, Decimal("50"), match_id)
        wallet_service.lock_stake(db, opponent.internal_id, Decimal("50"), match_id)

        wallet_service.settle_match_win(
            db, winner_id=test_user.internal_id, loser_id=opponent.internal_id,
            stake_amount=Decimal("50"), platform_fee=Decimal("5"), match_id=match_id,
        )

        # Second attempt at settling the SAME match must fail
        with pytest.raises(wallet_service.DuplicateTransactionError):
            wallet_service.settle_match_win(
                db, winner_id=test_user.internal_id, loser_id=opponent.internal_id,
                stake_amount=Decimal("50"), platform_fee=Decimal("5"), match_id=match_id,
            )

        # Winner should have exactly ONE payout's worth of money, not two
        winner_wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
        assert winner_wallet.available_balance == Decimal("95")
    finally:
        db.delete(opponent.wallet)
        db.delete(opponent)
        db.commit()


def test_settle_match_draw_refunds_both_players_fully(db, test_user):
    opponent = make_second_user(db)
    try:
        wallet_service.credit_deposit(db, test_user.internal_id, Decimal("50"), uuid.uuid4())
        wallet_service.credit_deposit(db, opponent.internal_id, Decimal("50"), uuid.uuid4())

        match_id = uuid.uuid4()
        wallet_service.lock_stake(db, test_user.internal_id, Decimal("50"), match_id)
        wallet_service.lock_stake(db, opponent.internal_id, Decimal("50"), match_id)

        wallet_service.settle_match_draw(
            db, player_a_id=test_user.internal_id, player_b_id=opponent.internal_id,
            stake_amount=Decimal("50"), match_id=match_id,
        )

        # Per your rule: draw = FULL refund, no fee deducted
        a_wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
        b_wallet = db.query(Wallet).filter(Wallet.user_id == opponent.internal_id).first()
        assert a_wallet.available_balance == Decimal("50")  # got their full stake back
        assert b_wallet.available_balance == Decimal("50")
        assert a_wallet.locked_balance == Decimal("0")
        assert b_wallet.locked_balance == Decimal("0")
    finally:
        db.delete(opponent.wallet)
        db.delete(opponent)
        db.commit()


# ------------------------------------------------------------------
# Withdrawals
# ------------------------------------------------------------------

def test_withdrawal_lock_then_reject_returns_funds(db, test_user):
    wallet_service.credit_deposit(db, test_user.internal_id, Decimal("100"), uuid.uuid4())

    withdrawal_id = uuid.uuid4()
    wallet_service.lock_withdrawal_amount(db, test_user.internal_id, Decimal("40"), withdrawal_id)

    wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
    assert wallet.available_balance == Decimal("60")
    assert wallet.locked_balance == Decimal("40")

    wallet_service.reject_withdrawal(db, test_user.internal_id, Decimal("40"), withdrawal_id)

    wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
    assert wallet.available_balance == Decimal("100")  # fully restored
    assert wallet.locked_balance == Decimal("0")


def test_withdrawal_lock_then_paid_removes_funds_permanently(db, test_user):
    wallet_service.credit_deposit(db, test_user.internal_id, Decimal("100"), uuid.uuid4())

    withdrawal_id = uuid.uuid4()
    wallet_service.lock_withdrawal_amount(db, test_user.internal_id, Decimal("40"), withdrawal_id)
    wallet_service.finalize_withdrawal_paid(db, test_user.internal_id, Decimal("40"), withdrawal_id)

    wallet = db.query(Wallet).filter(Wallet.user_id == test_user.internal_id).first()
    assert wallet.available_balance == Decimal("60")  # never comes back
    assert wallet.locked_balance == Decimal("0")
    assert wallet.total_withdrawals == Decimal("40")
