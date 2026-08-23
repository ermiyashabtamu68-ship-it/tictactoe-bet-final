"""
handlers/deposit.py

The manual deposit flow, step by step, exactly as specified:
  1. User selects Deposit
  2. Bot shows payment instructions (Telebirr or NIB Bank)
  3. User sends the actual payment themselves (outside the bot)
  4. User uploads a screenshot
  5. User enters the transaction/reference number
  6. Bot creates a PENDING deposit — balance is NOT touched yet
  7. Admin reviews later and approves/rejects (see admin panel)

We never credit the wallet here. That only happens after an admin
approves it (see routes/admin_deposits.py on the backend).
"""

from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from states import DepositStates
from keyboards import deposit_method_keyboard, main_menu_keyboard

router = Router()


@router.message(F.text == "➕ Deposit")
async def deposit_pressed(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "➕ <b>DEPOSIT</b>\n\nChoose your payment method:",
        reply_markup=deposit_method_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(DepositStates.choosing_method)


@router.callback_query(DepositStates.choosing_method, F.data.startswith("deposit_method:"))
async def deposit_method_chosen(callback: CallbackQuery, state: FSMContext, api):
    method = callback.data.split(":", 1)[1]

    if method == "cancel":
        await state.clear()
        await callback.message.edit_text("Cancelled.")
        await callback.answer()
        return

    from config import load_settings
    settings = load_settings()
    instructions = (
        settings.telebirr_instructions if method == "telebirr" else settings.nib_bank_instructions
    )

    await state.update_data(payment_method=method)
    await callback.message.edit_text(
        f"📋 <b>Payment Instructions</b>\n\n{instructions}\n\n"
        f"Once you've sent the payment, reply with the AMOUNT you sent (in ETB)."
    )
    await state.set_state(DepositStates.entering_amount)
    await callback.answer()


@router.message(DepositStates.entering_amount)
async def deposit_amount_entered(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, AttributeError):
        await message.answer("⚠️ Please enter a valid amount, e.g. 50")
        return

    await state.update_data(amount=str(amount))
    await message.answer("📸 Now upload a screenshot of your payment confirmation.")
    await state.set_state(DepositStates.awaiting_screenshot)


@router.message(DepositStates.awaiting_screenshot, F.photo)
async def deposit_screenshot_received(message: Message, state: FSMContext):
    # Telegram stores the photo and gives us a file_id we can use
    # later to re-fetch it — we save the id, not the image itself.
    file_id = message.photo[-1].file_id  # largest available size
    await state.update_data(screenshot_file_id=file_id)
    await message.answer(
        "🔢 Now enter the transaction/reference number from your payment."
    )
    await state.set_state(DepositStates.awaiting_reference_number)


@router.message(DepositStates.awaiting_screenshot)
async def deposit_screenshot_missing(message: Message):
    await message.answer("⚠️ Please upload a screenshot image (not text).")


@router.message(DepositStates.awaiting_reference_number)
async def deposit_reference_entered(message: Message, state: FSMContext, api):
    reference_number = message.text.strip()
    if not reference_number:
        await message.answer("⚠️ Please enter a valid reference number.")
        return

    data = await state.get_data()

    try:
        result = await api.create_deposit(
            telegram_user_id=message.from_user.id,
            amount=data["amount"],
            payment_method=data["payment_method"],
            reference_number=reference_number,
            screenshot_file_id=data["screenshot_file_id"],
        )
    except Exception:
        await message.answer(
            "⚠️ This reference number has already been submitted. "
            "If this is a mistake, contact support via ❓ Help.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"✅ <b>Deposit submitted!</b>\n\n"
        f"Amount: {data['amount']} ETB\n"
        f"Status: Pending review\n\n"
        f"An admin will verify your payment and credit your wallet shortly. "
        f"You can check status anytime in 📜 History.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
