"""ai_fast queue (`ai.classify`) and ai_deep queue (`ai.summarize`)."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import stages
from app.ai.errors import LLMConfigError, LLMInvalidOutput, LLMRateLimited
from app.config import settings
from app.jobs.errors import Reschedule
from app.jobs.queue import ClaimedJob, enqueue
from app.models import Item, ItemCluster, ItemStatus, Topic
from app.pipeline.steps import enqueue_next
from app.services import webpush
from app.services.clustering import best_enriched_member, elect_primary
from app.services.hotness import compute_hotness

logger = logging.getLogger(__name__)


def _covered_by(db: Session, item: Item) -> Item | None:
    """Don't spend tokens on an item that would be hidden anyway: its
    cluster already has an enriched member from an equal-or-better source."""
    if item.cluster_id is None:
        return None
    best = best_enriched_member(db, item.cluster_id, exclude_item_id=item.id)
    if best is not None and best.source.priority <= item.source.priority:
        return best
    return None


def _run_stage(job: ClaimedJob, item: Item, fn):
    """Maps provider errors onto job-pool semantics."""
    try:
        return fn()
    except LLMRateLimited as exc:
        raise Reschedule(exc.retry_after, str(exc), pause_queue=True) from exc
    except LLMConfigError as exc:
        # Not the item's fault: wait for the config to be fixed instead of
        # burning attempts or failing items.
        logger.error("AI misconfigured, item %s waits: %s", item.id, exc)
        raise Reschedule(600, f"config: {exc}", pause_queue=True) from exc
    except LLMInvalidOutput as exc:
        if job.is_last_attempt:
            item.status = ItemStatus.FAILED
            item.status_reason = f"invalid AI output: {exc}"[:300]
            return None
        raise


def handle_classify(db: Session, job: ClaimedJob) -> None:
    item = db.get(Item, job.payload["item_id"])
    if item is None or item.status != ItemStatus.READY:
        return

    covered = _covered_by(db, item)
    if covered is not None:
        item.status = ItemStatus.DUPLICATE
        item.duplicate_of_id = covered.id
        item.status_reason = f"same story already covered by {covered.source.slug}"
        return

    result = _run_stage(job, item, lambda: stages.classify(db, item))
    if result is None:
        return

    topic = db.execute(select(Topic).where(Topic.slug == result.output["topic"])).scalar_one_or_none()
    item.primary_topic_id = topic.id if topic else None
    item.relevance = result.output["relevance"]
    item.sentiment = result.output["sentiment"]

    if item.relevance < settings.AI_MIN_RELEVANCE:
        item.status = ItemStatus.FILTERED
        item.status_reason = f"relevance {item.relevance} < {settings.AI_MIN_RELEVANCE}"
        return
    item.status = ItemStatus.CLASSIFIED
    enqueue_next(db, item)


def handle_summarize(db: Session, job: ClaimedJob) -> None:
    item = db.get(Item, job.payload["item_id"])
    if item is None or item.status != ItemStatus.CLASSIFIED:
        return

    covered = _covered_by(db, item)
    if covered is not None:
        item.status = ItemStatus.DUPLICATE
        item.duplicate_of_id = covered.id
        item.status_reason = f"same story already covered by {covered.source.slug}"
        return

    topic_slug = item.topic.slug if item.topic else None
    result = _run_stage(job, item, lambda: stages.summarize(db, item, topic_slug))
    if result is None:
        return

    item.status = ItemStatus.ENRICHED
    item.status_reason = None
    item.enriched_at = datetime.now(timezone.utc)
    db.flush()

    source_count = 1
    if item.cluster_id is not None:
        cluster = db.get(ItemCluster, item.cluster_id)
        elect_primary(db, cluster)
        source_count = cluster.source_count
    else:
        item.is_duplicate = False

    item.hotness_score = compute_hotness(
        published_at=item.published_at,
        relevance=item.relevance,
        trust=item.source.trust,
        cluster_source_count=source_count,
    )

    fresh = item.published_at >= datetime.now(timezone.utc) - timedelta(hours=settings.PUSH_MAX_ITEM_AGE_HOURS)
    if (
        not item.is_duplicate
        and fresh
        and (item.relevance or 0) >= settings.PUSH_MIN_RELEVANCE
        and webpush.is_configured()
    ):
        enqueue(db, "deliver", "deliver.fanout", {"item_id": item.id}, dedupe_key=f"deliver.fanout:{item.id}")
