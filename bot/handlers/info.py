"""
handlers/info.py

The simpler read-only screens: Wallet, Profile, History, Help.
None of these change any data — they just display it.
"""

from aiogram import Router, F
from aiogram.types import Message

router = Router()


@router.message(F.text == "💰 Wallet")
async def wallet_pressed(message: Message, api):
    wallet = await api.get_wallet(message.from_user.id)
    await message.answer(
        f"💰 <b>YOUR WALLET</b>\n\n"
        f"Available: {wallet['available_balance']} ETB\n"
        f"Locked (in match/pending): {wallet['locked_balance']} ETB\n\n"
        f"🏆 Total winnings: {wallet['total_winnings']} ETB\n"
        f"🎮 Total games: {wallet['total_games']}\n"
        f"➕ Total deposits: {wallet['total_deposits']} ETB\n"
        f"💸 Total withdrawals: {wallet['total_withdrawals']} ETB",
        parse_mode="HTML",
    )


@router.message(F.text == "👤 Profile")
async def profile_pressed(message: Message):
    user = message.from_user
    await message.answer(
        f"👤 <b>YOUR PROFILE</b>\n\n"
        f"Name: {user.full_name}\n"
        f"Username: @{user.username if user.username else 'not set'}\n\n"
        f"Note: your account is identified internally by a unique "
        f"platform ID, not your Telegram username — so even if you "
        f"change your username, your balance and history stay safe.",
        parse_mode="HTML",
    )


@router.message(F.text == "📜 History")
async def history_pressed(message: Message, api):
    history = await api.get_history(message.from_user.id)
    matches = history.get("matches", [])

    if not matches:
        await message.answer("📜 No completed matches yet. Play your first game from 🎮 Play!")
        return

    lines = ["📜 <b>RECENT MATCHES</b>\n"]
    for m in matches[:10]:
        if m["status"] == "completed_draw":
            outcome = "🤝 Draw (refunded)"
        elif m["you_won"] is True:
            outcome = f"🏆 Won +{m['payout_amount']} ETB"
        elif m["you_won"] is False:
            outcome = f"❌ Lost -{m['stake_amount']} ETB"
        else:
            outcome = m["status"]
        lines.append(f"• {m['stake_amount']} ETB stake — {outcome}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text == "❓ Help")
async def help_pressed(message: Message):
    await message.answer(
        "❓ <b>HELP</b>\n\n"
        "🎮 <b>Play</b> — choose a stake, get matched, play Tic-Tac-Toe.\n"
        "💰 <b>Wallet</b> — view your balances.\n"
        "➕ <b>Deposit</b> — add funds (manually verified by admin).\n"
        "💸 <b>Withdraw</b> — request a payout (manually paid by admin).\n"
        "📜 <b>History</b> — your recent match results.\n\n"
        "📌 <b>Rules</b>\n"
        "• Platform fee: 5 ETB per completed match\n"
        "• Winner gets: total stakes − 5 ETB\n"
        "• Draw: both players fully refunded, no fee\n"
        "• No move within 45 seconds = forfeit\n\n"
        "For anything else, contact support.",
        parse_mode="HTML",
    )
