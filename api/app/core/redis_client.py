"""
core/redis_client.py

Sets up the connection to Redis, used only for matchmaking's
temporary "who's waiting" queues (see matchmaking_service.py).
"""

import os
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def get_redis():
    return redis_client
