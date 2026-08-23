"""
handlers/game.py

Handles taps on the Tic-Tac-Toe board itself. This file does NOT
decide who won or whether a move is valid — it just forwards the
tap to the backend (which uses match_service.py, the real referee)
and displays whatever the backend says happened.

This is what makes the game server-authoritative: even if someone
tampered with their Telegram client, the backend would still reject
an illegal move.
"""

import uuid

from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards import board_keyboard

router = Router()


@router.callback_query(F.data.startswith("move:"))
async def handle_move(callback: CallbackQuery, api):
    parts = callback.data.split(":")

    if parts[1] == "taken":
        await callback.answer("That square is already taken.", show_alert=False)
        return
    if parts[1] == "closed":
        await callback.answer("This match has ended.", show_alert=False)
        return

    match_id, cell_position = parts[1], int(parts[2])

    # A unique key per tap prevents the same move being applied twice
    # if Telegram retries the request (e.g. flaky connection causing
    # a double-send). Using the callback's own unique id is a simple,
    # reliable source for this.
    idempotency_key = f"move:{callback.id}"

    try:
        state = await api.make_move(
            match_id=match_id,
            telegram_user_id=callback.from_user.id,
            cell_position=cell_position,
            idempotency_key=idempotency_key,
        )
    except Exception as e:
        # Covers: not your turn, cell taken (race condition), match
        # already finished, etc. We show a friendly popup instead of
        # crashing the chat.
        await callback.answer("⚠️ That move wasn't allowed.", show_alert=True)
        return

    await _render_board(callback, state)
    await callback.answer()


async def _render_board(callback: CallbackQuery, state: dict):
    match_id = state["match_id"]
    board = state["board"]
    status = state["status"]

    if status == "active":
        turn_symbol = "❌" if state["current_turn"] == "X" else "⭕"
        text = f"Current turn: {turn_symbol} Player"
        keyboard = board_keyboard(board, match_id, is_finished=False)

    elif status == "completed_win":
        payout = state["payout_amount"]
        you_won = state.get("you_won")
        if you_won is True:
            headline = f"🏁 <b>You won!</b> 🎉"
        elif you_won is False:
            headline = f"🏁 <b>Match finished.</b> Your opponent won."
        else:
            headline = f"🏁 <b>Match finished!</b>"
        text = (
            f"{headline}\n\n"
            f"🏆 Winner takes {payout} ETB\n\n"
            f"Play again anytime from the 🎮 Play menu."
        )
        keyboard = board_keyboard(board, match_id, is_finished=True)

    elif status == "completed_forfeit":
        text = (
            f"🏁 <b>Match ended — timeout forfeit.</b>\n\n"
            f"A player didn't move within 45 seconds, so their "
            f"opponent wins the pot.\n\n"
            f"Play again anytime from the 🎮 Play menu."
        )
        keyboard = board_keyboard(board, match_id, is_finished=True)

    elif status == "completed_draw":
        text = (
            f"🤝 <b>It's a draw!</b>\n\n"
            f"Both players have been fully refunded their stake. "
            f"No fee was charged.\n\n"
            f"Play again anytime from the 🎮 Play menu."
        )
        keyboard = board_keyboard(board, match_id, is_finished=True)

    else:
        text = "Match ended."
        keyboard = board_keyboard(board, match_id, is_finished=True)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
