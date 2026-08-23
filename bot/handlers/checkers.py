"""
handlers/checkers.py

Checkers mode. Matchmaking (picking a stake, finding an opponent,
timing out if nobody's found) works exactly like Tic-Tac-Toe's — same
queue system, just tagged game_type="checkers" so the two games'
players never get paired together.

Actual gameplay does NOT happen in the chat like Tic-Tac-Toe's tap
buttons. Once matched, we send a button that opens the real visual
checkers board as a Telegram Mini App (checkers_app/). All moves
happen there; this file's job ends once the "Open Board" button is sent.
"""

import asyncio

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from keyboards import checkers_stake_selection_keyboard, open_checkers_board_keyboard, cancel_search_keyboard

router = Router()

POLL_INTERVAL_SECONDS = 3
POLL_MAX_ATTEMPTS = 40


@router.message(F.text == "🔴 Checkers")
async def checkers_pressed(message: Message):
    await message.answer(
        "🔴 <b>CHECKERS</b>\n\nChoose your stake:",
        reply_markup=checkers_stake_selection_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cxstake:"))
async def checkers_stake_chosen(callback: CallbackQuery, api, settings, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    if choice == "cancel":
        await callback.message.edit_text("Cancelled.")
        await callback.answer()
        return

    stake_amount = choice
    telegram_user_id = callback.from_user.id

    try:
        result = await api.join_checkers_queue(telegram_user_id, stake_amount)
    except Exception:
        await callback.message.edit_text(
            "⚠️ You don't have enough balance for this stake. Please deposit first."
        )
        await callback.answer()
        return

    if result["status"] == "matched":
        await _send_open_board_button(callback.message, api, settings, result["match_id"])
        await callback.answer()
        return

    await callback.message.edit_text("🔎 Finding opponent…", reply_markup=cancel_search_keyboard())
    await callback.answer()
    asyncio.create_task(
        _poll_for_checkers_match(callback.message, api, settings, telegram_user_id, state)
    )


async def _poll_for_checkers_match(message: Message, api, settings, telegram_user_id: int, state: FSMContext):
    for _ in range(POLL_MAX_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        data = await state.get_data()
        if data.get("search_cancelled"):
            await state.update_data(search_cancelled=False)
            return
        try:
            status = await api.check_match_status(telegram_user_id)
        except Exception:
            return
        if status["status"] == "matched":
            await _send_open_board_button(message, api, settings, status["match_id"])
            return
    await message.edit_text("⏱️ No opponent found in time. Please try again.")


async def _send_open_board_button(message: Message, api, settings, match_id: str):
    match = await api.get_match(match_id)
    await message.edit_text(
        f"✅ <b>Opponent found — Checkers</b>\n\n"
        f"💰 Stake: {match['stake_amount']} ETB\n\n"
        f"Tap below to open the board and play. Moves you make there "
        f"apply instantly — your opponent sees them live too.",
        reply_markup=open_checkers_board_keyboard(settings.public_api_base_url, match_id),
        parse_mode="HTML",
    )
