"""Shared Redis connection. Redis only holds rate-limit state (Groq token
buckets and daily counters, per-domain crawl spacing, robots.txt cache) —
never jobs; losing it just resets those limits."""

from functools import lru_cache

import redis

from app.config import settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
