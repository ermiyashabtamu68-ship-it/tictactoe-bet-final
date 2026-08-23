"""
Database models — mirrors the schema in db/migrations exactly.
Every table in the SQL migrations has a matching model here.
"""
import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, SmallInteger, BigInteger,
    Numeric, TIMESTAMP, ForeignKey, CheckConstraint, UniqueConstraint,
    Date, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def gen_uuid():
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    internal_id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    telegram_user_id = Column(BigInteger, nullable=False, unique=True, index=True)
    telegram_username = Column(Text)
    display_name = Column(Text)
    full_name = Column(Text)
    phone_number = Column(Text)
    status = Column(Text, nullable=False, default="active")
    date_of_birth = Column(Date)
    country_code = Column(Text)
    kyc_status = Column(Text, nullable=False, default="not_required")
    self_exclusion_until = Column(TIMESTAMP(timezone=True))
    registered_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_seen_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    wallet = relationship("Wallet", back_populates="user", uselist=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','suspended','self_excluded','banned')",
            name="chk_users_status"
        ),
        CheckConstraint(
            "kyc_status IN ('not_required','pending','verified','rejected')",
            name="chk_users_kyc_status"
        ),
    )


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.internal_id"), nullable=False, unique=True)
    available_balance = Column(Numeric(14, 2), nullable=False, default=0)
    locked_balance = Column(Numeric(14, 2), nullable=False, default=0)
    total_winnings = Column(Numeric(14, 2), nullable=False, default=0)
    total_games = Column(Integer, nullable=False, default=0)
    total_deposits = Column(Numeric(14, 2), nullable=False, default=0)
    total_withdrawals = Column(Numeric(14, 2), nullable=False, default=0)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="wallet")

    __table_args__ = (
        CheckConstraint("available_balance >= 0", name="chk_wallet_available_nonneg"),
        CheckConstraint("locked_balance >= 0", name="chk_wallet_locked_nonneg"),
    )


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False, index=True)
    type = Column(Text, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    balance_after = Column(Numeric(14, 2), nullable=False)
    locked_after = Column(Numeric(14, 2), nullable=False)
    reference_type = Column(Text)
    reference_id = Column(UUID(as_uuid=True))
    idempotency_key = Column(Text, nullable=False, unique=True)
    description = Column(Text)
    created_by_admin_id = Column(UUID(as_uuid=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "type IN ('deposit','withdrawal','stake_lock','stake_release','payout','fee','draw_refund','admin_adjustment')",
            name="chk_wallet_txn_type"
        ),
    )


class Deposit(Base):
    __tablename__ = "deposits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.internal_id"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    payment_method = Column(Text, nullable=False)
    reference_number = Column(Text, nullable=False)
    screenshot_file_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending", index=True)
    reviewed_by_admin_id = Column(UUID(as_uuid=True), ForeignKey("admins.id"))
    reviewed_at = Column(TIMESTAMP(timezone=True))
    rejection_reason = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_deposit_amount_positive"),
        CheckConstraint("payment_method IN ('telebirr','nib_bank')", name="chk_deposit_method"),
        CheckConstraint("status IN ('pending','approved','rejected')", name="chk_deposit_status"),
    )


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.internal_id"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    payment_method = Column(Text, nullable=False)
    payment_details = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending", index=True)
    reviewed_by_admin_id = Column(UUID(as_uuid=True), ForeignKey("admins.id"))
    reviewed_at = Column(TIMESTAMP(timezone=True))
    rejection_reason = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_withdrawal_amount_positive"),
        CheckConstraint("payment_method IN ('telebirr','nib_bank')", name="chk_withdrawal_method"),
        CheckConstraint("status IN ('pending','paid','rejected')", name="chk_withdrawal_status"),
    )


class Match(Base):
    __tablename__ = "matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    game_type = Column(Text, nullable=False, default="tictactoe", index=True)
    stake_amount = Column(Numeric(14, 2), nullable=False)
    platform_fee = Column(Numeric(14, 2), nullable=False, default=2.00)
    player_x_id = Column(UUID(as_uuid=True), ForeignKey("users.internal_id"), nullable=False, index=True)
    player_o_id = Column(UUID(as_uuid=True), ForeignKey("users.internal_id"), nullable=False, index=True)
    current_turn = Column(Text, nullable=False, default="X")
    board = Column(String(64), nullable=False, default="_________")
    status = Column(Text, nullable=False, default="active", index=True)
    winner_id = Column(UUID(as_uuid=True), ForeignKey("users.internal_id"))
    result_reason = Column(Text)
    payout_amount = Column(Numeric(14, 2))
    settled = Column(Boolean, nullable=False, default=False)
    settled_at = Column(TIMESTAMP(timezone=True))
    last_move_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    move_timeout_seconds = Column(Integer, nullable=False, default=45)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("stake_amount > 0", name="chk_match_stake_positive"),
        CheckConstraint("player_x_id <> player_o_id", name="chk_match_players_different"),
        CheckConstraint(
            "status IN ('active','completed_win','completed_draw','completed_forfeit','voided')",
            name="chk_match_status"
        ),
    )


class MatchMove(Base):
    __tablename__ = "match_moves"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False, index=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("users.internal_id"), nullable=False)
    symbol = Column(Text, nullable=False)
    cell_position = Column(SmallInteger, nullable=False)
    move_number = Column(Integer, nullable=False)
    idempotency_key = Column(Text, nullable=False, unique=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("symbol IN ('X','O')", name="chk_move_symbol"),
        CheckConstraint("cell_position BETWEEN 0 AND 8", name="chk_move_cell_range"),
        UniqueConstraint("match_id", "cell_position", name="uq_match_cell"),
        UniqueConstraint("match_id", "move_number", name="uq_match_move_number"),
    )


class CheckersMove(Base):
    """
    Separate from MatchMove (Tic-Tac-Toe's move log) because that
    table's constraints — cell_position 0-8 only, one row per cell —
    don't fit an 8x8 board where a square can be landed on many
    times over a game. Same purpose here though: mainly exists so
    idempotency_key can be checked, making retried requests safe.
    """
    __tablename__ = "checkers_moves"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False, index=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("users.internal_id"), nullable=False)
    symbol = Column(Text, nullable=False)
    from_position = Column(SmallInteger, nullable=False)
    to_position = Column(SmallInteger, nullable=False)
    move_number = Column(Integer, nullable=False)
    idempotency_key = Column(Text, nullable=False, unique=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("symbol IN ('X','O')", name="chk_checkers_move_symbol"),
        CheckConstraint("from_position BETWEEN 0 AND 63", name="chk_checkers_from_range"),
        CheckConstraint("to_position BETWEEN 0 AND 63", name="chk_checkers_to_range"),
        UniqueConstraint("match_id", "move_number", name="uq_checkers_match_move_number"),
    )


class Admin(Base):
    __tablename__ = "admins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    username = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(Text, nullable=False, default="admin")
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "role IN ('super_admin','admin','finance','support')",
            name="chk_admin_role"
        ),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    actor_type = Column(Text, nullable=False)
    actor_id = Column(UUID(as_uuid=True))
    action = Column(Text, nullable=False)
    target_type = Column(Text)
    target_id = Column(UUID(as_uuid=True))
    audit_metadata = Column("metadata", JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("actor_type IN ('admin','system','user')", name="chk_audit_actor_type"),
    )


class PlatformConfig(Base):
    __tablename__ = "platform_config"

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text)
    updated_by_admin_id = Column(UUID(as_uuid=True), ForeignKey("admins.id"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
