"""
handlers/withdraw.py

The withdrawal flow, step by step, as specified:
  1. User selects Withdraw
  2. Enter amount
  3. Enter approved withdrawal/payment details (their phone/account)
  4. Backend checks available balance is sufficient
  5. Creates a pending withdrawal, LOCKS the amount immediately
  6. Admin reviews and pays manually later
"""

from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from states import WithdrawStates
from keyboards import withdraw_method_keyboard, main_menu_keyboard

router = Router()


@router.message(F.text == "💸 Withdraw")
async def withdraw_pressed(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "💸 <b>WITHDRAW</b>\n\nChoose your withdrawal method:",
        reply_markup=withdraw_method_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(WithdrawStates.choosing_method)


@router.callback_query(WithdrawStates.choosing_method, F.data.startswith("withdraw_method:"))
async def withdraw_method_chosen(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split(":", 1)[1]

    if method == "cancel":
        await state.clear()
        await callback.message.edit_text("Cancelled.")
        await callback.answer()
        return

    await state.update_data(payment_method=method)
    await callback.message.edit_text("💵 Enter the amount you'd like to withdraw (in ETB):")
    await state.set_state(WithdrawStates.entering_amount)
    await callback.answer()


@router.message(WithdrawStates.entering_amount)
async def withdraw_amount_entered(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, AttributeError):
        await message.answer("⚠️ Please enter a valid amount, e.g. 100")
        return

    await state.update_data(amount=str(amount))
    data = await state.get_data()
    method_label = "Telebirr number" if data["payment_method"] == "telebirr" else "NIB Bank account number"
    await message.answer(f"📱 Enter your {method_label} to receive the payment:")
    await state.set_state(WithdrawStates.entering_payment_details)


@router.message(WithdrawStates.entering_payment_details)
async def withdraw_details_entered(message: Message, state: FSMContext, api):
    payment_details = message.text.strip()
    if not payment_details:
        await message.answer("⚠️ Please enter valid payment details.")
        return

    data = await state.get_data()

    try:
        result = await api.create_withdrawal(
            telegram_user_id=message.from_user.id,
            amount=data["amount"],
            payment_method=data["payment_method"],
            payment_details=payment_details,
        )
    except Exception:
        await message.answer(
            "⚠️ Insufficient available balance for this withdrawal.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"✅ <b>Withdrawal requested!</b>\n\n"
        f"Amount: {data['amount']} ETB\n"
        f"Status: Pending\n\n"
        f"This amount is now locked and an admin will send your payment shortly.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
