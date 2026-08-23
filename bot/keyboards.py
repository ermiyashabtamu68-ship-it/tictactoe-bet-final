"""
keyboards.py

All button layouts in one place. Keeping them here (instead of
scattered across handler files) makes it easy to change wording or
add buttons later without hunting through game logic.
"""

from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
)

STAKE_TIERS = ["10", "20", "50", "100"]


def deposit_method_keyboard() -> InlineKeyboardMarkup:
    """Shown when the player presses Deposit — choose payment method."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Telebirr", callback_data="deposit_method:telebirr")],
        [InlineKeyboardButton(text="🏦 NIB Bank", callback_data="deposit_method:nib_bank")],
        [InlineKeyboardButton(text="⬅️ Cancel", callback_data="deposit_method:cancel")],
    ])


def withdraw_method_keyboard() -> InlineKeyboardMarkup:
    """Shown when the player presses Withdraw — choose payment method."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Telebirr", callback_data="withdraw_method:telebirr")],
        [InlineKeyboardButton(text="🏦 NIB Bank", callback_data="withdraw_method:nib_bank")],
        [InlineKeyboardButton(text="⬅️ Cancel", callback_data="withdraw_method:cancel")],
    ])


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """The persistent bottom menu shown after /start."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Play"), KeyboardButton(text="🔴 Checkers")],
            [KeyboardButton(text="🎯 Play vs Friend")],
            [KeyboardButton(text="💰 Wallet")],
            [KeyboardButton(text="➕ Deposit"), KeyboardButton(text="💸 Withdraw")],
            [KeyboardButton(text="📜 History"), KeyboardButton(text="👤 Profile")],
            [KeyboardButton(text="❓ Help")],
        ],
        resize_keyboard=True,
    )


def stake_selection_keyboard() -> InlineKeyboardMarkup:
    """Shown when the player presses Play — pick a stake amount."""
    buttons = [
        InlineKeyboardButton(text=f"{s} ETB", callback_data=f"stake:{s}")
        for s in STAKE_TIERS
    ]
    # Two per row
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="⬅️ Cancel", callback_data="stake:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def friend_stake_selection_keyboard() -> InlineKeyboardMarkup:
    """Shown when the player presses Play vs Friend — pick a stake amount."""
    buttons = [
        InlineKeyboardButton(text=f"{s} ETB", callback_data=f"fstake:{s}")
        for s in STAKE_TIERS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="⬅️ Cancel", callback_data="fstake:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def challenge_response_keyboard() -> InlineKeyboardMarkup:
    """Shown to the friend being challenged — Accept or Decline."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Accept", callback_data="challenge:accept"),
            InlineKeyboardButton(text="❌ Decline", callback_data="challenge:decline"),
        ]
    ])


def cancel_search_keyboard() -> InlineKeyboardMarkup:
    """Shown while waiting for an opponent."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Cancel search", callback_data="search:cancel")]
    ])


def checkers_stake_selection_keyboard() -> InlineKeyboardMarkup:
    """Shown when the player presses 🔴 Checkers — pick a stake amount."""
    buttons = [
        InlineKeyboardButton(text=f"{s} ETB", callback_data=f"cxstake:{s}")
        for s in STAKE_TIERS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="⬅️ Cancel", callback_data="cxstake:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def open_checkers_board_keyboard(api_base_url: str, match_id: str) -> InlineKeyboardMarkup:
    """
    The button that opens the visual checkers board as a Telegram
    Mini App. The URL must be https (Telegram requires this for
    WebApp buttons) — api_base_url should be the API's public URL.
    """
    url = f"{api_base_url}/checkers-app/?match_id={match_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Open Board", web_app=WebAppInfo(url=url))]
    ])


def start_match_keyboard(match_id: str) -> InlineKeyboardMarkup:
    """Shown once an opponent is found, before the game starts."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Start Match", callback_data=f"match_start:{match_id}")]
    ])


def board_keyboard(board: str, match_id: str, is_finished: bool = False) -> InlineKeyboardMarkup:
    """
    Renders the 3x3 Tic-Tac-Toe board as tappable inline buttons.
    Occupied cells show X/O and are not tappable (callback goes to
    a harmless 'taken' handler). Empty cells show the cell number
    and are tappable.
    """
    symbols = {"_": None}
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            pos = r * 3 + c
            cell = board[pos]
            if cell == "_":
                label = str(pos + 1)
                callback = f"move:{match_id}:{pos}" if not is_finished else "move:closed"
            else:
                label = "❌" if cell == "X" else "⭕"
                callback = "move:taken"
            row.append(InlineKeyboardButton(text=label, callback_data=callback))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
