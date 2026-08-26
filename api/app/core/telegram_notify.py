"""
core/telegram_notify.py

The API needs to proactively message a player sometimes — mainly
when a Mini App friend invite is sent, since (unlike the old in-chat
"Play vs Friend" flow) there's no bot handler actively running at
that moment to message the invited friend directly.

The bot service still owns the actual conversation (it's the one
polling for updates and handling button taps), so we're not building
a second bot here — just making one HTTP call to Telegram's Bot API
to push a message using the same BOT_TOKEN. Telegram routes any
button taps on it back to the bot's normal polling loop exactly like
any other message, so its existing handlers just work.
"""

import os
import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    if not BOT_TOKEN:
        return  # Misconfigured — fail quietly rather than crash the caller's request.

    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        except Exception:
            pass  # Best-effort — the invite/challenge itself is already saved either way.


def challenge_response_markup() -> dict:
    """Mirrors keyboards.challenge_response_keyboard() exactly, so
    the SAME callback_data reaches the bot's existing accept/decline
    handlers in handlers/challenge.py — no new bot code needed."""
    return {
        "inline_keyboard": [[
            {"text": "✅ Accept", "callback_data": "challenge:accept"},
            {"text": "❌ Decline", "callback_data": "challenge:decline"},
        ]]
    }
