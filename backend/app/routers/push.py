"""Web Push subscription API (no accounts yet: a subscription is identified
by its endpoint URL, which only that browser knows)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import PushSubscription, Topic
from app.redis_client import get_redis
from app.schemas import PushConfigOut, PushEndpointRequest, PushStatusOut, PushSubscribeRequest
from app.services import webpush

router = APIRouter(prefix="/api/push", tags=["push"])

_ALLOWED_ENDPOINT_PREFIXES = ("https://",)


def _valid_topics(db: Session, slugs: list[str]) -> list[str]:
    known = set(db.execute(select(Topic.slug).where(Topic.is_public.is_(True))).scalars())
    unknown = sorted(set(slugs) - known)
    if unknown:
        raise HTTPException(422, f"unknown topics: {', '.join(unknown)}")
    return sorted(set(slugs))


@router.get("/config", response_model=PushConfigOut)
def push_config():
    if not webpush.is_configured():
        return PushConfigOut(enabled=False)
    return PushConfigOut(enabled=True, public_key=settings.VAPID_PUBLIC_KEY)


@router.post("/subscribe", response_model=PushStatusOut)
def subscribe(body: PushSubscribeRequest, request: Request, db: Session = Depends(get_db)):
    if not webpush.is_configured():
        raise HTTPException(503, "Web Push is not configured on the server")
    endpoint = body.subscription.endpoint
    if not endpoint.startswith(_ALLOWED_ENDPOINT_PREFIXES) or len(endpoint) > 2000:
        raise HTTPException(422, "invalid push endpoint")
    topics = _valid_topics(db, body.topics)
    now = datetime.now(timezone.utc)
    values = {
        "endpoint": endpoint,
        "p256dh": body.subscription.keys.p256dh[:200],
        "auth": body.subscription.keys.auth[:100],
        "topics": topics,
        "user_agent": (request.headers.get("user-agent") or "")[:300],
        "updated_at": now,
    }
    db.execute(
        pg_insert(PushSubscription)
        .values(**values)
        .on_conflict_do_update(index_elements=["endpoint"], set_={k: v for k, v in values.items() if k != "endpoint"})
    )
    db.commit()
    return PushStatusOut(subscribed=True, topics=topics)


@router.post("/status", response_model=PushStatusOut)
def status(body: PushEndpointRequest, db: Session = Depends(get_db)):
    sub = db.execute(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)).scalar_one_or_none()
    return PushStatusOut(subscribed=sub is not None, topics=list(sub.topics) if sub else [])


@router.post("/unsubscribe", response_model=PushStatusOut)
def unsubscribe(body: PushEndpointRequest, db: Session = Depends(get_db)):
    sub = db.execute(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)).scalar_one_or_none()
    if sub is not None:
        db.delete(sub)
        db.commit()
    return PushStatusOut(subscribed=False)


@router.post("/test")
def send_test(body: PushEndpointRequest, db: Session = Depends(get_db)):
    """Sends a test notification right away (max 1/minute per endpoint)."""
    sub = db.execute(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "subscription not found")
    if not get_redis().set(f"push:test:{sub.id}", "1", nx=True, ex=60):
        raise HTTPException(429, "Chỉ gửi thử được 1 lần mỗi phút")
    payload = webpush.build_payload(
        title="Tech Digest", body="Thông báo đã hoạt động 🎉", url="/", tag="test"
    )
    outcome = webpush.send(sub, payload)
    if outcome.gone:
        db.delete(sub)
        db.commit()
        raise HTTPException(410, "subscription expired — please enable notifications again")
    if not outcome.ok:
        raise HTTPException(502, f"push service error: {outcome.error}")
    return {"sent": True}
