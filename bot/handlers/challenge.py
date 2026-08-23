"""
handlers/challenge.py

The "Play vs Friend" flow: challenge a specific person by their
@username instead of waiting in the random matchmaking queue.

  1. Player A presses 🎯 Play vs Friend -> picks a stake
  2. Player A types their friend's @username
  3. Backend stores a pending challenge and tells us the friend's
     Telegram chat id
  4. We message Player B directly with Accept/Decline buttons
  5. If Player B accepts, the match is created (same stake-locking
     logic as random matchmaking) and BOTH players are shown the
     "opponent found" screen
"""

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from states import ChallengeStates
from keyboards import friend_stake_selection_keyboard, challenge_response_keyboard, start_match_keyboard
from handlers.play import _show_match_found

router = Router()


@router.message(F.text == "🎯 Play vs Friend")
async def play_vs_friend_pressed(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎯 <b>PLAY VS FRIEND</b>\n\nChoose the stake:",
        reply_markup=friend_stake_selection_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(ChallengeStates.choosing_stake)


@router.callback_query(ChallengeStates.choosing_stake, F.data.startswith("fstake:"))
async def friend_stake_chosen(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]

    if choice == "cancel":
        await state.clear()
        await callback.message.edit_text("Cancelled.")
        await callback.answer()
        return

    await state.update_data(challenge_stake=choice)
    await state.set_state(ChallengeStates.entering_username)
    await callback.message.edit_text(
        "👤 Type your friend's Telegram @username (they must have already "
        "started this bot):"
    )
    await callback.answer()


@router.message(ChallengeStates.entering_username)
async def friend_username_entered(message: Message, state: FSMContext, api, bot: Bot):
    opponent_username = message.text.strip()
    data = await state.get_data()
    stake_amount = data.get("challenge_stake")
    await state.clear()

    try:
        result = await api.create_challenge(message.from_user.id, opponent_username, stake_amount)
    except Exception as e:
        # The API returns a clear reason (not found / can't challenge
        # yourself / insufficient balance) — surface it as-is.
        detail = _extract_detail(e)
        await message.answer(f"⚠️ {detail}")
        return

    clean_username = opponent_username.lstrip("@")
    await message.answer(
        f"📨 Challenge sent to @{clean_username} for {stake_amount} ETB.\n"
        f"Waiting for them to respond (expires in 2 minutes)…"
    )

    # Message the friend directly — this works because they've
    # already started a chat with this same bot (required to be
    # findable by username in the first place).
    try:
        await bot.send_message(
            result["opponent_telegram_id"],
            f"🎯 <b>@{message.from_user.username or message.from_user.id} "
            f"challenged you to a match for {stake_amount} ETB!</b>",
            reply_markup=challenge_response_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(
            "⚠️ Couldn't reach your friend directly (they may have blocked "
            "the bot). The challenge is still saved — ask them to check."
        )


@router.callback_query(F.data == "challenge:accept")
async def challenge_accepted(callback: CallbackQuery, api, bot: Bot):
    try:
        result = await api.respond_challenge(callback.from_user.id, accept=True)
    except Exception as e:
        await callback.message.edit_text(f"⚠️ {_extract_detail(e)}")
        await callback.answer()
        return

    await _show_match_found(callback.message, api, result["match_id"])
    await callback.answer()

    # Also let the challenger know their friend accepted.
    try:
        match = await api.get_match(result["match_id"])
        await bot.send_message(
            result["challenger_telegram_id"],
            "✅ <b>Your friend accepted!</b>",
            reply_markup=start_match_keyboard(match["match_id"]),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data == "challenge:decline")
async def challenge_declined(callback: CallbackQuery, api, bot: Bot):
    try:
        result = await api.respond_challenge(callback.from_user.id, accept=False)
    except Exception as e:
        await callback.message.edit_text(f"⚠️ {_extract_detail(e)}")
        await callback.answer()
        return

    await callback.message.edit_text("You declined the challenge.")
    await callback.answer()

    try:
        await bot.send_message(result["challenger_telegram_id"], "❌ Your friend declined the challenge.")
    except Exception:
        pass


def _extract_detail(e: Exception) -> str:
    """Pulls the backend's HTTPException detail message out of an
    httpx error response, falling back to a generic message."""
    try:
        return e.response.json().get("detail", "Something went wrong.")
    except Exception:
        return "Something went wrong. Please try again."
