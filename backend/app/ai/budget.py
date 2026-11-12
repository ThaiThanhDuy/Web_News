"""Groq token budget, enforced *before* calling the API (Redis, shared by
every worker process):

  - a per-model token bucket refilled at GROQ_TPM_LIMIT tokens/minute
  - a per-model daily counter capped at GROQ_DAILY_TOKEN_CAP (UTC day)

reserve() takes an estimate up front; settle() corrects it with the real
`usage` the API returned. When the budget is spent the caller gets
LLMRateLimited(retry_after) and the job is rescheduled, not failed.
"""

import time
from datetime import datetime, timedelta, timezone

from app.ai.errors import LLMRateLimited
from app.config import settings
from app.redis_client import get_redis

# KEYS[1] bucket hash; ARGV: now_ms, capacity, refill_per_ms, cost
# Returns ms to wait (0 = reserved).
_BUCKET_LUA = """
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local rate = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1]) or capacity
local ts = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + (now - ts) * rate)
local wait = 0
if tokens >= cost then
  tokens = tokens - cost
else
  wait = math.ceil((cost - tokens) / rate)
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', KEYS[1], 120000)
return wait
"""


def _day_key(model: str) -> str:
    return f"llm:tokens:{model}:{datetime.now(timezone.utc):%Y%m%d}"


def _seconds_until_utc_midnight() -> float:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (tomorrow - now).total_seconds()


def estimate_tokens(*texts: str, max_output: int) -> int:
    # Vietnamese measured at ~2.7 chars/token on gpt-oss; 2.5 is conservative.
    return int(sum(len(t) for t in texts) / 2.5) + max_output


def reserve(model: str, tokens: int) -> None:
    redis = get_redis()
    used_today = int(redis.get(_day_key(model)) or 0)
    if used_today + tokens > settings.GROQ_DAILY_TOKEN_CAP:
        raise LLMRateLimited(
            f"daily token cap reached for {model} ({used_today}/{settings.GROQ_DAILY_TOKEN_CAP})",
            retry_after=_seconds_until_utc_midnight() + 60,
        )

    capacity = settings.GROQ_TPM_LIMIT
    cost = min(tokens, capacity)
    wait_ms = int(
        redis.eval(
            _BUCKET_LUA, 1, f"llm:bucket:{model}", int(time.time() * 1000), capacity, capacity / 60_000, cost
        )
    )
    if wait_ms > 0:
        raise LLMRateLimited(f"per-minute token budget for {model}", retry_after=wait_ms / 1000 + 1)

    pipe = redis.pipeline()
    pipe.incrby(_day_key(model), tokens)
    pipe.expire(_day_key(model), 2 * 86400)
    pipe.execute()


def settle(model: str, reserved: int, actual: int) -> None:
    """Replace the estimate with the real usage, in the daily counter and in
    the minute bucket — estimates reserve the full max output (e.g. 1,200
    tokens for a summary that really uses ~250), and leaving that unused
    reservation in the bucket would throttle us well below the real limit."""
    delta = actual - reserved
    if not delta:
        return
    redis = get_redis()
    redis.incrby(_day_key(model), delta)
    bucket = f"llm:bucket:{model}"
    if redis.exists(bucket):
        # Refund (or charge) the difference; refill caps it at capacity.
        redis.hincrbyfloat(bucket, "tokens", -delta)


def refund(model: str, reserved: int) -> None:
    """The call didn't happen / wasn't billed (e.g. a network error)."""
    get_redis().decrby(_day_key(model), reserved)


def used_today(model: str) -> int:
    return int(get_redis().get(_day_key(model)) or 0)
