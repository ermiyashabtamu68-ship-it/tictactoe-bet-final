"""
schemas.py

Defines the exact "shape" of data the API accepts and returns.
FastAPI uses these to automatically validate incoming requests
(e.g. reject a deposit with a negative amount before it ever
reaches our code) and to generate API documentation for free.
"""

from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional


class RegisterUserRequest(BaseModel):
    telegram_user_id: int
    telegram_username: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None


class DepositRequest(BaseModel):
    telegram_user_id: int
    amount: Decimal = Field(gt=0)
    payment_method: str  # 'telebirr' or 'nib_bank'
    reference_number: str
    screenshot_file_id: str


class WithdrawalRequest(BaseModel):
    telegram_user_id: int
    amount: Decimal = Field(gt=0)
    payment_method: str
    payment_details: str


class JoinQueueRequest(BaseModel):
    telegram_user_id: int
    stake_amount: Decimal = Field(gt=0)
    game_type: str = "tictactoe"


class CheckersMoveRequest(BaseModel):
    telegram_user_id: int
    from_position: int = Field(ge=0, le=63)
    to_position: int = Field(ge=0, le=63)
    idempotency_key: str


class WebAppCheckersMoveRequest(BaseModel):
    # No telegram_user_id here on purpose — the Mini App identifies
    # the player via the signed X-Telegram-Init-Data header instead,
    # which can't be spoofed the way a plain request field could.
    from_position: int = Field(ge=0, le=63)
    to_position: int = Field(ge=0, le=63)
    idempotency_key: str


class CreateChallengeRequest(BaseModel):
    telegram_user_id: int
    opponent_username: str
    stake_amount: Decimal = Field(gt=0)


class RespondChallengeRequest(BaseModel):
    telegram_user_id: int
    accept: bool


class MakeMoveRequest(BaseModel):
    telegram_user_id: int
    cell_position: int = Field(ge=0, le=8)
    idempotency_key: str


class AdminReviewRequest(BaseModel):
    admin_id: str
    reason: Optional[str] = None
