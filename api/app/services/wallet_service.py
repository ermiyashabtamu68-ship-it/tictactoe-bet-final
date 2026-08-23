"""
wallet_service.py

This file is the ONLY place in the whole project allowed to change
a user's balance. Nothing else should touch wallet numbers directly.

Why centralize it like this? Because money bugs are the most dangerous
kind of bug. If 5 different files each had their own code to "add
money" or "remove money", it would be very easy for one of them to
have a mistake that lets someone cheat the system. By forcing every
money movement through this one file, we only have to get it right
in one place.

Every function here follows the same safety pattern:
1. Lock the wallet row in the database (so two things can't change
   the same wallet at the exact same time)
2. Check the change is actually allowed (e.g. enough balance)
3. Update the wallet numbers
4. Write a permanent record row in wallet_transactions (the ledger)
5. Commit everything together, or nothing at all (atomic transaction)

If any step fails, EVERYTHING is rolled back — so a wallet can never
end up in a broken half-updated state.
"""

import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.models import Wallet, WalletTransaction


class InsufficientBalanceError(Exception):
    """Raised when a user tries to spend/withdraw/lock more than they have."""
    pass


class DuplicateTransactionError(Exception):
    """
    Raised when the same idempotency_key is used twice.
    This is what stops a match from being paid out twice, or a
    deposit from being credited twice if a button is pressed twice.
    """
    pass


def _get_locked_wallet(db: Session, user_id: uuid.UUID) -> Wallet:
    """
    Fetches a user's wallet AND locks it so no other request can
    change it until this database transaction finishes.

    Think of it like picking up a shared notebook: while you're
    writing in it, nobody else can write in it at the same time.
    This is what prevents two matches settling at once and both
    trying to update the same wallet, causing a wrong final balance.
    """
    wallet = (
        db.query(Wallet)
        .filter(Wallet.user_id == user_id)
        .with_for_update()  # <-- this is the actual "lock" instruction to Postgres
        .first()
    )
    if wallet is None:
        raise ValueError(f"No wallet found for user {user_id}")
    return wallet


def _write_ledger_row(
    db: Session,
    wallet: Wallet,
    txn_type: str,
    amount: Decimal,
    idempotency_key: str,
    reference_type: str = None,
    reference_id: uuid.UUID = None,
    description: str = None,
    admin_id: uuid.UUID = None,
) -> WalletTransaction:
    """
    Writes one permanent row to wallet_transactions.

    This row is a snapshot: it records the balances AFTER this change,
    so even if someone deletes everything else, this table alone tells
    the full history of every ETB that moved.

    idempotency_key must be unique. If the same key is used twice,
    the database itself will reject the second attempt (see the
    UNIQUE constraint in the migration). We catch that here and turn
    it into a clear error instead of a confusing database crash.
    """
    txn = WalletTransaction(
        wallet_id=wallet.id,
        type=txn_type,
        amount=amount,
        balance_after=wallet.available_balance,
        locked_after=wallet.locked_balance,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        description=description,
        created_by_admin_id=admin_id,
    )
    db.add(txn)
    try:
        db.flush()  # forces the UNIQUE constraint check now, not later
    except IntegrityError:
        db.rollback()
        raise DuplicateTransactionError(
            f"Transaction with idempotency_key '{idempotency_key}' already processed."
        )
    return txn


# ------------------------------------------------------------------
# DEPOSITS
# ------------------------------------------------------------------

def credit_deposit(
    db: Session,
    user_id: uuid.UUID,
    amount: Decimal,
    deposit_id: uuid.UUID,
) -> WalletTransaction:
    """
    Adds money to a user's AVAILABLE balance.
    Call this ONLY after an admin has approved a deposit — never
    when the user first submits it.
    """
    wallet = _get_locked_wallet(db, user_id)

    wallet.available_balance += amount
    wallet.total_deposits += amount

    # idempotency_key is tied to the deposit_id, so the same deposit
    # can never be credited twice even if this function is called
    # twice by accident (e.g. admin double-clicks Approve).
    idempotency_key = f"deposit:{deposit_id}"

    txn = _write_ledger_row(
        db, wallet,
        txn_type="deposit",
        amount=amount,
        idempotency_key=idempotency_key,
        reference_type="deposit",
        reference_id=deposit_id,
        description=f"Deposit approved: {amount} ETB",
    )
    db.commit()
    return txn


# ------------------------------------------------------------------
# WITHDRAWALS
# ------------------------------------------------------------------

def lock_withdrawal_amount(
    db: Session,
    user_id: uuid.UUID,
    amount: Decimal,
    withdrawal_id: uuid.UUID,
) -> WalletTransaction:
    """
    Called the moment a user REQUESTS a withdrawal (before admin pays).
    Moves money from available -> locked, so the user can't spend it
    on a match while the withdrawal is pending.
    """
    wallet = _get_locked_wallet(db, user_id)

    if wallet.available_balance < amount:
        raise InsufficientBalanceError(
            f"User {user_id} has {wallet.available_balance} available, "
            f"cannot lock {amount} for withdrawal."
        )

    wallet.available_balance -= amount
    wallet.locked_balance += amount

    idempotency_key = f"withdrawal_lock:{withdrawal_id}"
    txn = _write_ledger_row(
        db, wallet,
        txn_type="withdrawal",
        amount=-amount,
        idempotency_key=idempotency_key,
        reference_type="withdrawal",
        reference_id=withdrawal_id,
        description=f"Withdrawal requested, funds locked: {amount} ETB",
    )
    db.commit()
    return txn


def finalize_withdrawal_paid(
    db: Session,
    user_id: uuid.UUID,
    amount: Decimal,
    withdrawal_id: uuid.UUID,
) -> WalletTransaction:
    """
    Called when admin marks a withdrawal as PAID (money actually sent
    manually via Telebirr/bank). Removes the money permanently from
    locked_balance — it's gone, it left the platform.
    """
    wallet = _get_locked_wallet(db, user_id)

    wallet.locked_balance -= amount
    wallet.total_withdrawals += amount

    idempotency_key = f"withdrawal_paid:{withdrawal_id}"
    txn = _write_ledger_row(
        db, wallet,
        txn_type="withdrawal",
        amount=Decimal("0"),  # already deducted from available at lock time; this just clears locked
        idempotency_key=idempotency_key,
        reference_type="withdrawal",
        reference_id=withdrawal_id,
        description=f"Withdrawal paid out: {amount} ETB",
    )
    db.commit()
    return txn


def reject_withdrawal(
    db: Session,
    user_id: uuid.UUID,
    amount: Decimal,
    withdrawal_id: uuid.UUID,
) -> WalletTransaction:
    """
    Called when admin REJECTS a withdrawal. Returns the locked amount
    back to available_balance so the user can use it again.
    """
    wallet = _get_locked_wallet(db, user_id)

    wallet.locked_balance -= amount
    wallet.available_balance += amount

    idempotency_key = f"withdrawal_reject:{withdrawal_id}"
    txn = _write_ledger_row(
        db, wallet,
        txn_type="withdrawal",
        amount=amount,
        idempotency_key=idempotency_key,
        reference_type="withdrawal",
        reference_id=withdrawal_id,
        description=f"Withdrawal rejected, funds returned: {amount} ETB",
    )
    db.commit()
    return txn


# ------------------------------------------------------------------
# MATCH STAKES
# ------------------------------------------------------------------

def lock_stake(
    db: Session,
    user_id: uuid.UUID,
    stake_amount: Decimal,
    match_id: uuid.UUID,
) -> WalletTransaction:
    """
    Called when a player joins a match. Moves their stake from
    available -> locked. This is what makes "do not allow a player
    to join a match without sufficient balance" actually enforced —
    if they don't have enough, InsufficientBalanceError is raised
    and the match never starts.
    """
    wallet = _get_locked_wallet(db, user_id)

    if wallet.available_balance < stake_amount:
        raise InsufficientBalanceError(
            f"User {user_id} has {wallet.available_balance} available, "
            f"cannot stake {stake_amount}."
        )

    wallet.available_balance -= stake_amount
    wallet.locked_balance += stake_amount

    idempotency_key = f"stake_lock:{match_id}:{user_id}"
    txn = _write_ledger_row(
        db, wallet,
        txn_type="stake_lock",
        amount=-stake_amount,
        idempotency_key=idempotency_key,
        reference_type="match",
        reference_id=match_id,
        description=f"Stake locked for match: {stake_amount} ETB",
    )
    db.commit()
    return txn


def settle_match_win(
    db: Session,
    winner_id: uuid.UUID,
    loser_id: uuid.UUID,
    stake_amount: Decimal,
    platform_fee: Decimal,
    match_id: uuid.UUID,
) -> dict:
    """
    Called ONCE when a match ends with a winner (line win or timeout
    forfeit). Pays the winner (pot - fee), and clears the loser's
    locked stake (it's gone — that was their loss).

    This function is protected against double-settlement in two ways:
    1. idempotency_key on the ledger rows (database-enforced)
    2. the caller (match_service) must check match.settled == False
       inside the same locked transaction before calling this.

    total pot = stake + stake
    winner payout = pot - platform_fee
    """
    pot = stake_amount * 2
    payout = pot - platform_fee

    # --- Winner: their own locked stake converts into the payout ---
    winner_wallet = _get_locked_wallet(db, winner_id)
    winner_wallet.locked_balance -= stake_amount
    winner_wallet.available_balance += payout
    winner_wallet.total_winnings += payout
    winner_wallet.total_games += 1

    winner_txn = _write_ledger_row(
        db, winner_wallet,
        txn_type="payout",
        amount=payout,
        idempotency_key=f"payout:{match_id}:{winner_id}",
        reference_type="match",
        reference_id=match_id,
        description=f"Match won. Pot {pot} - fee {platform_fee} = payout {payout} ETB",
    )

    # --- Loser: their locked stake is simply removed (transferred to winner + fee) ---
    loser_wallet = _get_locked_wallet(db, loser_id)
    loser_wallet.locked_balance -= stake_amount
    loser_wallet.total_games += 1

    loser_txn = _write_ledger_row(
        db, loser_wallet,
        txn_type="payout",
        amount=Decimal("0"),
        idempotency_key=f"payout_loss:{match_id}:{loser_id}",
        reference_type="match",
        reference_id=match_id,
        description=f"Match lost. Stake {stake_amount} ETB forfeited.",
    )

    db.commit()
    return {"winner_txn": winner_txn, "loser_txn": loser_txn, "payout": payout}


def settle_match_draw(
    db: Session,
    player_a_id: uuid.UUID,
    player_b_id: uuid.UUID,
    stake_amount: Decimal,
    match_id: uuid.UUID,
) -> dict:
    """
    Called ONCE when a match ends in a draw.
    Per platform rule: FULL refund to both players, NO fee charged.
    Locked stake simply moves back to available for both.
    """
    txns = {}
    for label, player_id in (("player_a", player_a_id), ("player_b", player_b_id)):
        wallet = _get_locked_wallet(db, player_id)
        wallet.locked_balance -= stake_amount
        wallet.available_balance += stake_amount
        wallet.total_games += 1

        txn = _write_ledger_row(
            db, wallet,
            txn_type="draw_refund",
            amount=stake_amount,
            idempotency_key=f"draw_refund:{match_id}:{player_id}",
            reference_type="match",
            reference_id=match_id,
            description=f"Match drawn. Full refund: {stake_amount} ETB",
        )
        txns[label] = txn

    db.commit()
    return txns


def release_single_stake(
    db: Session,
    user_id: uuid.UUID,
    stake_amount: Decimal,
    match_id: uuid.UUID,
    reason: str = "match_creation_failed",
) -> WalletTransaction:
    """
    Refunds ONE player's locked stake back to available. Used when a
    match fails to fully start (e.g. player A's stake got locked but
    player B turned out to have insufficient balance) — player A
    should not be left with money stuck in 'locked' for a match that
    never happened.
    """
    wallet = _get_locked_wallet(db, user_id)
    wallet.locked_balance -= stake_amount
    wallet.available_balance += stake_amount

    idempotency_key = f"stake_release_single:{match_id}:{user_id}"
    txn = _write_ledger_row(
        db, wallet,
        txn_type="stake_release",
        amount=stake_amount,
        idempotency_key=idempotency_key,
        reference_type="match",
        reference_id=match_id,
        description=f"Stake released ({reason}): {stake_amount} ETB",
    )
    db.commit()
    return txn


def void_match_refund(
    db: Session,
    player_a_id: uuid.UUID,
    player_b_id: uuid.UUID,
    stake_amount: Decimal,
    match_id: uuid.UUID,
    reason: str = "admin_void",
) -> dict:
    """
    Called if a match needs to be cancelled by an admin (e.g. a bug,
    a dispute, both players disconnect). Same effect as a draw refund:
    both players get their stake back, no fee.
    """
    txns = {}
    for label, player_id in (("player_a", player_a_id), ("player_b", player_b_id)):
        wallet = _get_locked_wallet(db, player_id)
        wallet.locked_balance -= stake_amount
        wallet.available_balance += stake_amount

        txn = _write_ledger_row(
            db, wallet,
            txn_type="stake_release",
            amount=stake_amount,
            idempotency_key=f"void_refund:{match_id}:{player_id}",
            reference_type="match",
            reference_id=match_id,
            description=f"Match voided ({reason}). Refund: {stake_amount} ETB",
        )
        txns[label] = txn

    db.commit()
    return txns


# ------------------------------------------------------------------
# ADMIN ADJUSTMENTS
# ------------------------------------------------------------------

def admin_adjust_balance(
    db: Session,
    user_id: uuid.UUID,
    amount: Decimal,  # positive to add, negative to subtract
    admin_id: uuid.UUID,
    reason: str,
    adjustment_id: uuid.UUID,
) -> WalletTransaction:
    """
    The ONLY way an admin can change a user's balance directly.
    Unlike every other function here, this is a manual override —
    so it REQUIRES a reason and always records which admin did it.
    This satisfies the rule: "Never allow admins to directly edit a
    user's balance without creating an audited adjustment transaction."
    """
    if not reason or not reason.strip():
        raise ValueError("admin_adjust_balance requires a non-empty reason.")

    wallet = _get_locked_wallet(db, user_id)

    if amount < 0 and wallet.available_balance < abs(amount):
        raise InsufficientBalanceError(
            f"Cannot deduct {abs(amount)}, user only has {wallet.available_balance} available."
        )

    wallet.available_balance += amount

    idempotency_key = f"admin_adjustment:{adjustment_id}"
    txn = _write_ledger_row(
        db, wallet,
        txn_type="admin_adjustment",
        amount=amount,
        idempotency_key=idempotency_key,
        reference_type="admin",
        reference_id=admin_id,
        description=f"Admin adjustment: {reason}",
        admin_id=admin_id,
    )
    db.commit()
    return txn
