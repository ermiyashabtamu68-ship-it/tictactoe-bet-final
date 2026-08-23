"""
core/rate_limit.py

Prevents someone from hammering the API with requests — e.g.
trying thousands of admin passwords per second, or spamming the
move endpoint to cause chaos. Uses Redis to track request counts,
so limits are shared correctly even if you later run more than one
API server.
"""

import os
from slowapi import Limiter
from slowapi.util import get_remote_address

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

limiter = Limiter(
    key_func=get_remote_address,   # limits are per IP address
    storage_uri=REDIS_URL,
    default_limits=["100/minute"],  # generous default for normal use
)
