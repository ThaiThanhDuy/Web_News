"""ai_fast queue (`ai.classify`) and ai_deep queue (`ai.summarize`)."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai import stages
from app.ai.errors import LLMConfigError, LLMInvalidOutput, LLMRateLimited
from app.config import settings
from app.jobs.errors import Reschedule
from app.jobs.queue import ClaimedJob, enqueue
from app.models import Item, ItemCluster, ItemStatus, Job, JobStatus, Topic, TopicItem
from app.pipeline.steps import enqueue_next
from app.services import local_classifier, webpush
from app.services.clustering import best_enriched_member, elect_primary
from app.services.ranking import rescore_one
from app.services.search_index import index_item

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


def _link_topics(db: Session, item: Item, related: list[str]) -> None:
    """topic_items = the primary topic + the summary's related topics."""
    db.execute(delete(TopicItem).where(TopicItem.item_id == item.id))
    if item.primary_topic_id:
        db.add(TopicItem(item_id=item.id, topic_id=item.primary_topic_id, is_primary=True))
    if related:
        for topic_id in db.execute(select(Topic.id).where(Topic.slug.in_(related))).scalars():
            if topic_id != item.primary_topic_id:
                db.add(TopicItem(item_id=item.id, topic_id=topic_id, is_primary=False))


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


# Classify yields while this many summaries are waiting (see below).
SUMMARIZE_BACKLOG_LIMIT = 3


def _stages_share_quota() -> bool:
    if settings.LLM_PROVIDER.strip().lower() == "ollama":
        return True  # one local model serves both stages
    return settings.CLASSIFY_MODEL == settings.SUMMARIZE_MODEL


def _summaries_waiting(db: Session) -> int:
    """Summarize jobs that are due now or soon (not ones parked until the
    daily quota resets)."""
    soon = datetime.now(timezone.utc) + timedelta(minutes=5)
    return db.execute(
        select(func.count())
        .select_from(Job)
        .where(Job.queue == "ai_deep", Job.status == JobStatus.QUEUED, Job.run_at <= soon)
    ).scalar_one()


def _too_old(item: Item) -> bool:
    """Stale news isn't worth tokens (AI_MAX_ITEM_AGE_HOURS)."""
    if not settings.AI_MAX_ITEM_AGE_HOURS:
        return False
    return item.published_at < datetime.now(timezone.utc) - timedelta(hours=settings.AI_MAX_ITEM_AGE_HOURS)


def _drop_if_too_old(item: Item) -> bool:
    if not _too_old(item):
        return False
    item.status = ItemStatus.FILTERED
    item.status_reason = f"older than {settings.AI_MAX_ITEM_AGE_HOURS}h when its AI turn came"
    return True


def handle_classify(db: Session, job: ClaimedJob) -> None:
    item = db.get(Item, job.payload["item_id"])
    if item is None or item.status != ItemStatus.READY:
        return
    if _drop_if_too_old(item):
        return

    # When both stages draw on the same token quota, finishing items comes
    # first: a classified-but-unsummarized item is invisible, and classify's
    # smaller requests would otherwise grab every refill of the per-minute
    # budget and starve summarize (seen in practice: 164 classifies vs 3
    # summaries in a day). So classify waits while summaries are pending.
    if _stages_share_quota() and _summaries_waiting(db) >= SUMMARIZE_BACKLOG_LIMIT:
        raise Reschedule(20, "summaries first (shared token quota)", pause_queue=True)

    covered = _covered_by(db, item)
    if covered is not None:
        item.status = ItemStatus.DUPLICATE
        item.duplicate_of_id = covered.id
        item.status_reason = f"same story already covered by {covered.source.slug}"
        return

    # Single-topic sources never need the classify call (normally they skip
    # this stage in filter.item; this covers items queued before that rule).
    if item.source.default_topic:
        topic = db.execute(select(Topic).where(Topic.slug == item.source.default_topic)).scalar_one_or_none()
        if topic is not None:
            item.primary_topic_id = topic.id
            item.status = ItemStatus.CLASSIFIED
            item.status_reason = "topic from source (classify skipped)"
            db.flush()
            enqueue_next(db, item)
            return

    # Local kNN classifier first (no tokens) — only when it has proven
    # accurate enough; otherwise / when unsure, the AI decides.
    local = local_classifier.predict(db, item.id, item.embedding)
    if local is not None:
        topic = db.execute(select(Topic).where(Topic.slug == local.topic)).scalar_one_or_none()
        if topic is not None:
            item.primary_topic_id = topic.id
            if not settings.follows_topic(local.topic):
                item.status = ItemStatus.FILTERED
                item.status_reason = f"topic not followed: {local.topic} (local {local.confidence:.0%})"
                return
            item.status = ItemStatus.CLASSIFIED
            item.status_reason = f"topic by local classifier ({local.confidence:.0%})"
            db.flush()
            enqueue_next(db, item)
            return

    result = _run_stage(job, item, lambda: stages.classify(db, item))
    if result is None:
        return

    topic = db.execute(select(Topic).where(Topic.slug == result.output["topic"])).scalar_one_or_none()
    item.primary_topic_id = topic.id if topic else None
    item.relevance = result.output["relevance"]
    item.sentiment = result.output["sentiment"]

    if not settings.follows_topic(result.output["topic"]):
        # Not one of the followed topics: stop here, no summarize tokens.
        item.status = ItemStatus.FILTERED
        item.status_reason = f"topic not followed: {result.output['topic']}"
        return
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
    if _drop_if_too_old(item):
        return

    covered = _covered_by(db, item)
    if covered is not None:
        item.status = ItemStatus.DUPLICATE
        item.duplicate_of_id = covered.id
        item.status_reason = f"same story already covered by {covered.source.slug}"
        return

    if item.source.default_topic and (item.topic is None or item.topic.slug != item.source.default_topic):
        # Classified by AI before the source got its default topic: the
        # source's topic is authoritative.
        topic = db.execute(select(Topic).where(Topic.slug == item.source.default_topic)).scalar_one_or_none()
        if topic is not None:
            item.primary_topic_id = topic.id
            db.flush()
            db.refresh(item, ["topic"])
    topic_slug = item.topic.slug if item.topic else None
    if not settings.follows_topic(topic_slug):
        # Classified before FOLLOWED_TOPICS changed: drop it, don't summarize.
        item.status = ItemStatus.FILTERED
        item.status_reason = f"topic not followed: {topic_slug}"
        return
    result = _run_stage(job, item, lambda: stages.summarize(db, item, topic_slug))
    if result is None:
        return

    # Items that skipped classify take relevance/sentiment from the summary.
    if item.relevance is None:
        item.relevance = result.output["relevance"]
    if item.sentiment is None:
        item.sentiment = result.output["sentiment"]
    _link_topics(db, item, result.output.get("related_topics") or [])
    item.status = ItemStatus.ENRICHED
    item.status_reason = None
    item.enriched_at = datetime.now(timezone.utc)
    index_item(item, result.output, item.topic.name if item.topic else None)
    db.flush()

    if item.cluster_id is not None:
        elect_primary(db, db.get(ItemCluster, item.cluster_id))
    else:
        item.is_duplicate = False

    rescore_one(db, item)

    fresh = item.published_at >= datetime.now(timezone.utc) - timedelta(hours=settings.PUSH_MAX_ITEM_AGE_HOURS)
    if (
        not item.is_duplicate
        and fresh
        and (item.relevance or 0) >= settings.PUSH_MIN_RELEVANCE
        and webpush.is_configured()
    ):
        enqueue(db, "deliver", "deliver.fanout", {"item_id": item.id}, dedupe_key=f"deliver.fanout:{item.id}")
