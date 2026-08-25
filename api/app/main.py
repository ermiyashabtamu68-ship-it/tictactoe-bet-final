"""
main.py

The entry point for the backend. This is what actually starts when
you run the API — it creates the FastAPI app and plugs in every
route file we've built so far.
"""

import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.core.rate_limit import limiter
from app.routes import (
    users, deposits, withdrawals, matchmaking, matches, challenges, friends, webapp,
    admin_auth, admin_deposits, admin_withdrawals,
    admin_dashboard, admin_users,
)
from app.core.database import SessionLocal
from app.services import match_service
from app.models.models import Match

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tictactoe-bet")

app = FastAPI(title="TicTacToe Bet API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Allows the admin panel (running on a different address/port) to
# call this API from a browser. In production, restrict this to
# your actual admin panel's domain instead of "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, tags=["users"])
app.include_router(deposits.router, tags=["deposits"])
app.include_router(withdrawals.router, tags=["withdrawals"])
app.include_router(matchmaking.router, tags=["matchmaking"])
app.include_router(matches.router, tags=["matches"])
app.include_router(challenges.router, tags=["challenges"])
app.include_router(friends.router, tags=["friends"])
app.include_router(webapp.router, tags=["webapp"])
app.include_router(admin_auth.router, tags=["admin"])
app.include_router(admin_deposits.router, tags=["admin"])
app.include_router(admin_withdrawals.router, tags=["admin"])
app.include_router(admin_dashboard.router, tags=["admin"])
app.include_router(admin_users.router, tags=["admin"])

# Serves the admin panel (plain HTML/CSS/JS) at /admin-panel/
# The panel itself talks to this same API using JavaScript fetch()
# calls, exactly like the bot does.
app.mount("/admin-panel", StaticFiles(directory="/app/admin_static", html=True), name="admin_panel")

# Serves the checkers Mini App (visual board) at /checkers-app/
# Opened from inside Telegram via a WebApp button the bot sends.
app.mount("/checkers-app", StaticFiles(directory="/app/checkers_static", html=True), name="checkers_app")

# Serves the Tic-Tac-Toe Mini App (visual board) at /tictactoe-app/
# Same idea as checkers above — opened via a WebApp button.
app.mount("/tictactoe-app", StaticFiles(directory="/app/tictactoe_static", html=True), name="tictactoe_app")

# Serves the FULL Mini App — wallet, deposit, withdraw, play, friends,
# history, profile — all in one place at /app/. This is what the bot's
# single "🚀 Open App" button launches.
app.mount("/app-ui", StaticFiles(directory="/app/webapp_static", html=True), name="full_app")

# Deposit proof images uploaded directly through the Mini App (as
# opposed to via a Telegram chat message, which the bot flow uses)
# are saved here and streamed back only to logged-in admins via the
# /admin/deposits/{id}/screenshot route — this mount is NOT public.
os.makedirs("/app/uploads", exist_ok=True)


@app.get("/health")
def health_check():
    """Simple endpoint to confirm the API is alive - useful for Docker health checks."""
    return {"status": "ok"}


async def timeout_checker_loop():
    """
    Runs forever in the background, checking every few seconds for
    any active match where the current player has run out of time.
    This is what actually enforces the 45-second move timeout —
    without this loop, a match would just sit there forever if a
    player walked away.
    """
    while True:
        await asyncio.sleep(5)
        db = SessionLocal()
        try:
            active_matches = db.query(Match.id).filter(Match.status == "active").all()
            for (match_id,) in active_matches:
                try:
                    match_service.check_and_apply_timeout(db, match_id)
                except Exception:
                    logger.exception(f"Error checking timeout for match {match_id}")
        finally:
            db.close()


@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(timeout_checker_loop())
    logger.info("Timeout checker background task started.")
