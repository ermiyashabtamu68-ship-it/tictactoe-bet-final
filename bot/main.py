"""
main.py (bot)

The entry point for the Telegram bot. This is what actually starts
when you run the bot — it connects to Telegram, loads every handler
file we've built, and starts listening for messages.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from config import load_settings
from api_client import ApiClient
from handlers import start, play, game, deposit, withdraw, info, challenge, checkers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tictactoe-bot")


async def main():
    settings = load_settings()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # FSM storage backed by Redis (not memory) so that if the bot
    # restarts, players in the middle of "searching for opponent"
    # or mid-conversation flows (like entering a deposit reference
    # number) don't lose their place.
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    api = ApiClient(base_url=settings.api_base_url)

    # Every handler function can request `api` as a parameter (as
    # we've been writing them) — this line is what makes that work,
    # by injecting the same ApiClient instance into every handler call.
    dp["api"] = api
    dp["settings"] = settings

    dp.include_router(start.router)
    dp.include_router(play.router)
    dp.include_router(challenge.router)
    dp.include_router(checkers.router)
    dp.include_router(game.router)
    dp.include_router(deposit.router)
    dp.include_router(withdraw.router)
    dp.include_router(info.router)

    logger.info("Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
