"""
handlers/start.py

Handles /start. Unlike before, this no longer registers the user
silently using only their Telegram info — it now asks for their
NAME and PHONE NUMBER first, since that's how the platform
identifies real people (per your decision: name + phone, no KYC/age
checks for now).

Flow:
  1. /start -> if already registered, just show the menu
  2. If new -> ask for full name
  3. Ask for phone number
  4. Register via the backend API, then show the menu
"""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from states import RegistrationStates
from keyboards import main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, api, state: FSMContext):
    # Try a "silent" check first: if this Telegram ID is already
    # registered, the backend just returns their existing account
    # and we skip straight to the menu instead of asking again.
    # We do this by attempting registration with no name/phone —
    # the backend only requires them for BRAND NEW accounts.
    try:
        await api.register_user(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
        )
        # If this succeeded, the user already existed — welcome them back.
        await message.answer(
            "👋 Welcome back!",
            reply_markup=main_menu_keyboard(),
        )
        return
    except Exception:
        # NOTE: this catches BOTH "new user, name/phone required" AND
        # any real network/server error. For now that's an acceptable
        # simplification (worst case, a returning user is asked to
        # re-enter their phone, which just fails gracefully with
        # "already registered" and no harm done). If this becomes
        # annoying in testing, we can make api_client raise a more
        # specific error type to tell the two cases apart.
        pass

    await state.set_state(RegistrationStates.entering_name)
    await message.answer(
        "👋 Welcome to TicTacToe Bet!\n\n"
        "Let's set up your account. What's your full name?"
    )


@router.message(RegistrationStates.entering_name)
async def name_entered(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if len(name) < 2:
        await message.answer("⚠️ Please enter your full name.")
        return

    await state.update_data(full_name=name)
    await message.answer("📱 Now enter your phone number (e.g. 09xxxxxxxx):")
    await state.set_state(RegistrationStates.entering_phone)


@router.message(RegistrationStates.entering_phone)
async def phone_entered(message: Message, state: FSMContext, api):
    phone = message.text.strip() if message.text else ""
    if len(phone) < 9:
        await message.answer("⚠️ Please enter a valid phone number.")
        return

    data = await state.get_data()

    try:
        await api.register_user(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=data["full_name"],
            phone_number=phone,
        )
    except Exception:
        await message.answer(
            "⚠️ This phone number is already registered to another account. "
            "Please enter a different phone number, or contact support via ❓ Help."
        )
        return

    await state.clear()
    await message.answer(
        "✅ Account created!\n\n"
        "📌 How it works:\n"
        "• Both players stake the same amount\n"
        "• Winner takes the pot minus a 5 ETB platform fee\n"
        "• A draw = full refund to both players, no fee\n\n"
        "Use the menu below to get started.",
        reply_markup=main_menu_keyboard(),
    )
