"""
api_client.py

The bot NEVER touches the database directly. Instead, it sends
requests to the FastAPI backend (like a phone app talking to a
server), and the backend does the real work using the wallet_service
and match_service files we already built.

Why split it this way? Because the backend is "the source of truth"
and can be trusted. The bot is just a friendly front-end. If we ever
add a website or mobile app later, they'd talk to the same backend
API without needing to touch the bot code at all.
"""

import httpx


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def _post(self, path: str, json: dict) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{self.base_url}{path}", json=json)
            response.raise_for_status()
            return response.json()

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    # ---------------- Users ----------------

    async def register_user(
        self, telegram_user_id: int, username: str | None,
        full_name: str | None = None, phone_number: str | None = None,
    ) -> dict:
        return await self._post("/users/register", {
            "telegram_user_id": telegram_user_id,
            "telegram_username": username,
            "full_name": full_name,
            "phone_number": phone_number,
        })

    async def get_wallet(self, telegram_user_id: int) -> dict:
        return await self._get(f"/wallet/{telegram_user_id}")

    # ---------------- Deposits ----------------

    async def create_deposit(
        self, telegram_user_id: int, amount: str, payment_method: str,
        reference_number: str, screenshot_file_id: str
    ) -> dict:
        return await self._post("/deposits", {
            "telegram_user_id": telegram_user_id,
            "amount": amount,
            "payment_method": payment_method,
            "reference_number": reference_number,
            "screenshot_file_id": screenshot_file_id,
        })

    # ---------------- Withdrawals ----------------

    async def create_withdrawal(
        self, telegram_user_id: int, amount: str, payment_method: str, payment_details: str
    ) -> dict:
        return await self._post("/withdrawals", {
            "telegram_user_id": telegram_user_id,
            "amount": amount,
            "payment_method": payment_method,
            "payment_details": payment_details,
        })

    # ---------------- Matchmaking & Matches ----------------

    async def join_queue(self, telegram_user_id: int, stake_amount: str, game_type: str = "tictactoe") -> dict:
        return await self._post("/matchmaking/join", {
            "telegram_user_id": telegram_user_id,
            "stake_amount": stake_amount,
            "game_type": game_type,
        })

    async def join_checkers_queue(self, telegram_user_id: int, stake_amount: str) -> dict:
        return await self.join_queue(telegram_user_id, stake_amount, game_type="checkers")

    async def check_match_status(self, telegram_user_id: int) -> dict:
        return await self._get(f"/matchmaking/status/{telegram_user_id}")

    async def leave_queue(self, telegram_user_id: int, stake_amount: str, game_type: str = "tictactoe") -> dict:
        return await self._post("/matchmaking/leave", {
            "telegram_user_id": telegram_user_id,
            "stake_amount": stake_amount,
            "game_type": game_type,
        })

    async def create_challenge(self, telegram_user_id: int, opponent_username: str, stake_amount: str) -> dict:
        return await self._post("/challenges", {
            "telegram_user_id": telegram_user_id,
            "opponent_username": opponent_username,
            "stake_amount": stake_amount,
        })

    async def respond_challenge(self, telegram_user_id: int, accept: bool) -> dict:
        return await self._post("/challenges/respond", {
            "telegram_user_id": telegram_user_id,
            "accept": accept,
        })

    async def get_match(self, match_id: str) -> dict:
        return await self._get(f"/matches/{match_id}")

    async def make_move(
        self, match_id: str, telegram_user_id: int, cell_position: int, idempotency_key: str
    ) -> dict:
        return await self._post(f"/matches/{match_id}/move", {
            "telegram_user_id": telegram_user_id,
            "cell_position": cell_position,
            "idempotency_key": idempotency_key,
        })

    async def checkers_move(
        self, match_id: str, telegram_user_id: int, from_position: int, to_position: int, idempotency_key: str
    ) -> dict:
        return await self._post(f"/matches/{match_id}/checkers-move", {
            "telegram_user_id": telegram_user_id,
            "from_position": from_position,
            "to_position": to_position,
            "idempotency_key": idempotency_key,
        })

    # ---------------- History ----------------

    async def get_history(self, telegram_user_id: int) -> dict:
        return await self._get(f"/users/{telegram_user_id}/history")
