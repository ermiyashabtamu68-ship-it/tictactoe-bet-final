"""
core/database.py

Sets up the connection to PostgreSQL and provides a fresh database
"session" (a temporary workspace for talking to the DB) for each
API request. FastAPI automatically calls get_db() for any route
that asks for it, and closes the session afterward — so we never
have to remember to clean up manually.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/tictactoe_bet"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
