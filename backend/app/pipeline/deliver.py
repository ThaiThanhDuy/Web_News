"""deliver queue: `deliver.fanout` creates one delivery row per matching
push subscription (BEFORE anything is sent), `deliver.send` sends one.
A re-run never notifies twice: deliveries are unique per (subscription,
item, channel) and send only acts on `pending` rows."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.jobs.errors import Reschedule
from app.jobs.queue import ClaimedJob, enqueue
from app.models import Delivery, Enrichment, Item, ItemStatus, PushSubscription
from app.services import webpush

logger = logging.getLogger(__name__)


def handle_fanout(db: Session, job: ClaimedJob) -> None:
    item = db.get(Item, job.payload["item_id"])
    if item is None or item.status != ItemStatus.ENRICHED or item.is_duplicate or not webpush.is_configured():
        return

    topic_slug = item.topic.slug if item.topic else None
    conditions = [PushSubscription.topics == []]
    if topic_slug:
        conditions.append(PushSubscription.topics.contains([topic_slug]))
    subscriptions = db.execute(select(PushSubscription).where(or_(*conditions))).scalars().all()

    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    queued = 0
    for sub in subscriptions:
        sent_last_hour = db.execute(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.subscription_id == sub.id, Delivery.status == "sent", Delivery.sent_at >= hour_ago)
        ).scalar_one()
        status = "skipped" if sent_last_hour >= settings.PUSH_MAX_PER_HOUR else "pending"
        delivery_id = db.execute(
            pg_insert(Delivery)
            .values(
                subscription_id=sub.id,
                item_id=item.id,
                channel="webpush",
                status=status,
                error="hourly cap reached" if status == "skipped" else None,
            )
            .on_conflict_do_nothing(constraint="uq_deliveries_recipient_item_channel")
            .returning(Delivery.id)
        ).scalar_one_or_none()
        if delivery_id is not None and status == "pending":
            enqueue(db, "deliver", "deliver.send", {"delivery_id": delivery_id}, dedupe_key=f"deliver.send:{delivery_id}")
            queued += 1
    if queued:
        logger.info("item %s: %s push deliveries queued", item.id, queued)


def latest_takeaway(db: Session, item_id: int) -> str:
    output = db.execute(
        select(Enrichment.output)
        .where(Enrichment.item_id == item_id, Enrichment.stage == "summarize")
        .order_by(Enrichment.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (output or {}).get("one_line_takeaway") or ""


def handle_send(db: Session, job: ClaimedJob) -> None:
    delivery = db.get(Delivery, job.payload["delivery_id"])
    if delivery is None or delivery.status != "pending":
        return
    subscription = db.get(PushSubscription, delivery.subscription_id)
    item = db.get(Item, delivery.item_id)
    if subscription is None or item is None:
        return

    payload = webpush.build_payload(
        title=item.title, body=latest_takeaway(db, item.id), url=item.url, tag=f"item-{item.id}"
    )
    outcome = webpush.send(subscription, payload)
    now = datetime.now(timezone.utc)
    if outcome.ok:
        delivery.status = "sent"
        delivery.sent_at = now
        subscription.last_sent_at = now
    elif outcome.gone:
        logger.info("push subscription %s is gone (%s); deleting it", subscription.id, outcome.error)
        db.delete(subscription)  # cascades to its deliveries
    elif outcome.retry_after is not None:
        raise Reschedule(outcome.retry_after, f"push service rate limit: {outcome.error}")
    elif outcome.transient and not job.is_last_attempt:
        raise RuntimeError(f"push send failed, will retry: {outcome.error}")
    else:
        delivery.status = "failed"
        delivery.error = (outcome.error or "unknown error")[:2000]
