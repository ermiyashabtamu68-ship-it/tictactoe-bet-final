"""
handlers/play.py

Handles the whole "find an opponent" flow:
  1. Player presses 🎮 Play -> shown stake options
  2. Player picks a stake -> bot asks backend to join the queue
  3. If matched immediately -> show opponent found
  4. If not matched yet -> bot checks again every few seconds
     (this is called "polling") until an opponent joins, or the
     player cancels

Why polling instead of instant push? Telegram bots don't have a way
for the backend to "interrupt" a specific chat the instant something
happens elsewhere — polling (checking "did anything change yet?"
every few seconds) is the simple, reliable way to handle this
without extra infrastructure. It's not instant, but a few seconds
of delay is completely fine for matchmaking.
"""

import asyncio

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from keyboards import (
    stake_selection_keyboard, cancel_search_keyboard,
    start_match_keyboard, board_keyboard,
)

router = Router()

POLL_INTERVAL_SECONDS = 3
POLL_MAX_ATTEMPTS = 40  # ~2 minutes of searching before giving up


@router.message(F.text == "🎮 Play")
async def play_pressed(message: Message):
    await message.answer(
        "🎮 <b>PLAY</b>\n\nChoose your stake:",
        reply_markup=stake_selection_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("stake:"))
async def stake_chosen(callback: CallbackQuery, api, state: FSMContext):
    choice = callback.data.split(":", 1)[1]

    if choice == "cancel":
        await callback.message.edit_text("Cancelled.")
        await callback.answer()
        return

    stake_amount = choice
    telegram_user_id = callback.from_user.id

    # Remember which stake this player is searching at, so Cancel
    # and the poll loop know what to leave/check. FSMContext storage
    # is backed by Redis (configured in main.py), so this survives
    # even if the bot process restarts.
    await state.update_data(searching_stake=stake_amount)

    try:
        result = await api.join_queue(telegram_user_id, stake_amount)
    except Exception:
        await callback.message.edit_text(
            "⚠️ You don't have enough balance for this stake. "
            "Please deposit first."
        )
        await callback.answer()
        return

    if result["status"] == "matched":
        await _show_match_found(callback.message, api, result["match_id"])
        await callback.answer()
        return

    # Not matched yet — show searching message and start polling
    await callback.message.edit_text(
        "🔎 Finding opponent…",
        reply_markup=cancel_search_keyboard(),
    )
    await callback.answer()

    asyncio.create_task(
        _poll_for_match(callback.message, api, telegram_user_id, stake_amount, state)
    )


@router.callback_query(F.data == "search:cancel")
async def cancel_search(callback: CallbackQuery, api, state: FSMContext):
    data = await state.get_data()
    stake_amount = data.get("searching_stake")

    if stake_amount:
        await api.leave_queue(callback.from_user.id, stake_amount)

    await state.update_data(searching_stake=None, search_cancelled=True)
    await callback.message.edit_text("Search cancelled.")
    await callback.answer()


async def _poll_for_match(message: Message, api, telegram_user_id: int, stake_amount: str, state: FSMContext):
    """
    Checks every few seconds whether this player has been matched
    while they wait. Stops after POLL_MAX_ATTEMPTS (~2 minutes) and
    tells them to try again, so nobody waits forever silently.
    Also stops early if the player pressed Cancel.
    """
    for _ in range(POLL_MAX_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

        data = await state.get_data()
        if data.get("search_cancelled"):
            await state.update_data(search_cancelled=False)
            return  # player cancelled, stop polling quietly

        try:
            status = await api.check_match_status(telegram_user_id)
        except Exception:
            return  # balance issue or similar; stop polling silently

        if status["status"] == "matched":
            await _show_match_found(message, api, status["match_id"])
            return

    await message.edit_text("⏱️ No opponent found in time. Please try again.")


async def _show_match_found(message: Message, api, match_id: str):
    match = await api.get_match(match_id)
    stake = match["stake_amount"]
    payout = float(stake) * 2 - 2

    await message.edit_text(
        f"✅ <b>Opponent found!</b>\n\n"
        f"💰 Stake: {stake} ETB\n"
        f"🏆 Winner prize: {payout:.0f} ETB\n\n"
        f"ℹ️ Draws are fully refunded. No moves within 45 seconds "
        f"forfeits the match.",
        reply_markup=start_match_keyboard(match_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("match_start:"))
async def start_match(callback: CallbackQuery, api):
    match_id = callback.data.split(":", 1)[1]
    match = await api.get_match(match_id)

    turn_symbol = "❌" if match["current_turn"] == "X" else "⭕"
    await callback.message.edit_text(
        f"Current turn: {turn_symbol} Player",
        reply_markup=board_keyboard(match["board"], match_id),
    )
    await callback.answer()
