"""parse queue (`parse.item`): normalize, language, exact-duplicate check.
filter queue (`filter.item`): rules, near-duplicate SimHash, embedding and
same-story clustering. Both are cheap and deterministic — they run before
any token is spent."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.jobs.queue import ClaimedJob
from app.models import Item, ItemStatus, Topic
from app.pipeline.steps import enqueue_next
from app.services.clustering import assign_cluster
from app.utils.text import content_hash, detect_language, hamming64, simhash64

logger = logging.getLogger(__name__)

_NOT_DEDUPE_TARGETS = (ItemStatus.FILTERED, ItemStatus.FAILED)


def _text(item: Item) -> str:
    return item.content or item.feed_summary or ""


def handle_parse_item(db: Session, job: ClaimedJob) -> None:
    item = db.get(Item, job.payload["item_id"])
    if item is None:
        return
    expected = ItemStatus.DISCOVERED if item.item_type == "video" else ItemStatus.FETCHED
    if item.status != expected:
        return

    text = _text(item)
    item.language = detect_language(f"{item.title}\n{text}")
    item.content_hash = content_hash(item.title, text)

    duplicate_of = db.execute(
        select(Item.id)
        .where(
            Item.content_hash == item.content_hash,
            Item.id != item.id,
            Item.status.notin_(_NOT_DEDUPE_TARGETS),
        )
        .order_by(Item.id)
        .limit(1)
    ).scalar_one_or_none()
    if duplicate_of is not None:
        item.status = ItemStatus.DUPLICATE
        item.duplicate_of_id = duplicate_of
        item.status_reason = "exact duplicate (same content hash)"
        return

    item.status = ItemStatus.PARSED
    enqueue_next(db, item)


def handle_filter_item(db: Session, job: ClaimedJob) -> None:
    item = db.get(Item, job.payload["item_id"])
    if item is None or item.status != ItemStatus.PARSED:
        return

    text = _text(item)
    combined = f"{item.title}\n{text}"

    # 1) rules
    reason = None
    if len(item.title.strip()) < settings.MIN_TITLE_CHARS:
        reason = "title too short"
    elif len(combined.strip()) < settings.MIN_CONTENT_CHARS:
        reason = "content too short"
    else:
        lowered = combined.lower()
        hit = next((k for k in settings.blocked_keywords if k in lowered), None)
        if hit:
            reason = f"blocked keyword: {hit}"
    if reason:
        item.status = ItemStatus.FILTERED
        item.status_reason = reason
        return

    # 2) near-duplicate text (syndicated copies, light edits)
    item.simhash = simhash64(combined)
    window_start = datetime.now(timezone.utc) - timedelta(hours=settings.NEAR_DUP_WINDOW_HOURS)
    candidates = db.execute(
        select(Item.id, Item.simhash).where(
            Item.simhash.is_not(None),
            Item.id != item.id,
            Item.published_at >= window_start,
            Item.status.notin_(_NOT_DEDUPE_TARGETS),
        )
    ).all()
    for other_id, other_hash in candidates:
        if hamming64(item.simhash, other_hash) <= settings.SIMHASH_MAX_DISTANCE:
            item.status = ItemStatus.DUPLICATE
            item.duplicate_of_id = other_id
            item.status_reason = "near duplicate (SimHash)"
            return

    # 3) same story from another source (embeddings), when enabled
    if settings.EMBEDDINGS_ENABLED:
        from app.services.embeddings import embed_text  # heavy import (torch) only when used

        item.embedding = embed_text(combined)
        assign_cluster(db, item)

    # Single-topic sources (economy desks): the topic is known, so skip the
    # AI classify call and go straight to summarize.
    if item.source.default_topic:
        topic = db.execute(select(Topic).where(Topic.slug == item.source.default_topic)).scalar_one_or_none()
        if topic is not None:
            item.primary_topic_id = topic.id
            item.status = ItemStatus.CLASSIFIED
            item.status_reason = "topic from source (classify skipped)"
            db.flush()
            enqueue_next(db, item)
            return

    item.status = ItemStatus.READY
    enqueue_next(db, item)
