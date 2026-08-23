"""
core/telegram_auth.py

Validates the `initData` string Telegram gives every Mini App
(WebApp) when it opens. This is how we prove a request claiming to
be "Telegram user 12345" is REALLY from that person, and not just
someone hand-crafting an HTTP request with a fake id — important
here because moves affect real money.

Algorithm is Telegram's official one:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# How old an initData payload can be before we reject it. Telegram
# reissues a fresh one every time the Mini App is opened, so this is
# generous just to allow for clock drift / a slow network.
MAX_INIT_DATA_AGE_SECONDS = 86400


class InvalidInitDataError(Exception):
    pass


def verify_init_data(init_data: str) -> dict:
    """
    Verifies the signature and freshness of `init_data`, then returns
    the Telegram user's info as a dict (id, username, first_name...).
    Raises InvalidInitDataError if anything is wrong.
    """
    if not BOT_TOKEN:
        raise InvalidInitDataError("Server misconfigured: BOT_TOKEN not set on the API service.")
    if not init_data:
        raise InvalidInitDataError("Missing Telegram init data.")

    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        raise InvalidInitDataError("Malformed init data.")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InvalidInitDataError("Init data is missing its signature.")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InvalidInitDataError("Init data signature doesn't match — request rejected.")

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if time.time() - auth_date > MAX_INIT_DATA_AGE_SECONDS:
        raise InvalidInitDataError("Init data has expired — please reopen the game from the bot.")

    user_raw = parsed.get("user")
    if not user_raw:
        raise InvalidInitDataError("No user info in init data.")

    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        raise InvalidInitDataError("Malformed user info in init data.")
