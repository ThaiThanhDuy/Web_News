"""Anonymous reader events (impressions, clicks, hashtag clicks, push opens,
searches) → aggregate counters (services/engagement.py).

Accepts the body as text/plain JSON so browsers can send it with
navigator.sendBeacon (no CORS preflight). Nothing identifying is stored; the
client IP is used only, unstored, for a per-minute rate limit in Redis.
"""

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.redis_client import get_redis
from app.services import engagement

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])

MAX_BODY_BYTES = 32_000


class EventIn(BaseModel):
    type: Literal["impression", "click", "tag_click", "push_open", "search"]
    item_id: int | None = Field(None, ge=1)
    position: int | None = Field(None, ge=1, le=1000)
    query: str | None = Field(None, max_length=200)


class EventBatch(BaseModel):
    events: list[EventIn] = Field(..., max_length=50)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return (forwarded.split(",")[0].strip() if forwarded else None) or (request.client.host if request.client else "?")


@router.post("", status_code=204)
async def ingest(request: Request, db: Session = Depends(get_db)) -> Response:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(413, "too many events")
    try:
        batch = EventBatch.model_validate(json.loads(body or b"{}"))
    except (ValueError, ValidationError):
        raise HTTPException(422, "invalid events") from None
    if not batch.events:
        return Response(status_code=204)

    try:
        redis = get_redis()
        key = f"events:rate:{_client_ip(request)}"
        used = redis.incrby(key, len(batch.events))
        if used == len(batch.events):
            redis.expire(key, 60)
        if used > settings.EVENTS_MAX_PER_MINUTE:
            raise HTTPException(429, "slow down")
    except HTTPException:
        raise
    except Exception:  # Redis down: accept rather than lose the batch
        logger.warning("events rate limiter unavailable")

    engagement.ingest(
        db,
        [engagement.Event(type=e.type, item_id=e.item_id, position=e.position, query=e.query) for e in batch.events],
    )
    db.commit()
    return Response(status_code=204)
