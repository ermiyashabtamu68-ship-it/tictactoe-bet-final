"""
config.py

All settings the bot needs, loaded from environment variables (set
in the .env file, never hard-coded here). This keeps secrets like
the bot token OUT of the code itself — important because this code
may end up on GitHub where Yafet and Nahom can see it, but the
actual token should stay private to whoever runs the bot.
"""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    bot_token: str
    api_base_url: str          # where the FastAPI backend lives, e.g. http://api:8000
    public_api_base_url: str   # the PUBLIC https URL of the API — needed for Mini App buttons,
                                # since Telegram opens WebApp links in the user's browser/app,
                                # not over Railway's internal network like api_base_url is.
    redis_url: str
    telebirr_instructions: str
    nib_bank_instructions: str


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Check your .env file.")

    api_base_url = os.getenv("API_BASE_URL", "http://api:8000")

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is not set. Check your .env file.")

    return Settings(
        bot_token=bot_token,
        api_base_url=api_base_url,
        redis_url=redis_url,
        public_api_base_url=os.getenv("PUBLIC_API_BASE_URL", api_base_url),
        telebirr_instructions=os.getenv(
            "TELEBIRR_INSTRUCTIONS",
            "Send payment to Telebirr number: [SET IN .env]\nThen upload your screenshot and enter the reference number."
        ),
        nib_bank_instructions=os.getenv(
            "NIB_BANK_INSTRUCTIONS",
            "Send payment to NIB Bank account: [SET IN .env]\nThen upload your screenshot and enter the reference number."
        ),
    )