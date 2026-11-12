"""maintenance queue: lease reaper, hotness refresh, retention cleanup, and
reconcile (re-creates the next job for any item stuck without one)."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.jobs.queue import ClaimedJob, reap_expired_leases
from app.models import (
    Delivery,
    FetchRun,
    Item,
    ItemCluster,
    ItemStatus,
    Job,
    JobStatus,
    KeywordDaily,
    SearchQueryDaily,
)
from app.pipeline.steps import dedupe_key, enqueue_next, next_step
from app.services import raw_store
from app.services.clustering import elect_primary
from app.services import local_classifier, youtube_stats
from app.services.ranking import rescore
from app.services.trends import refresh_keyword_daily, refresh_trends

logger = logging.getLogger(__name__)

# A dead job is retried by reconcile after this long (transient outages).
DEAD_JOB_RETRY_HOURS = 6
STUCK_AFTER_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def handle_reap(db: Session, job: ClaimedJob) -> None:
    count = reap_expired_leases(db)
    if count:
        logger.warning("reaper: %s jobs had expired leases", count)


def handle_hotness(db: Session, job: ClaimedJob) -> None:
    """Freshness decays and trends/engagement move: re-rank recent items."""
    window_start = _now() - timedelta(hours=settings.HOTNESS_WINDOW_HOURS)
    items = db.execute(
        select(Item).where(
            Item.status == ItemStatus.ENRICHED, Item.is_duplicate.is_(False), Item.published_at >= window_start
        )
    ).scalars().all()
    rescore(db, list(items))


def handle_trends(db: Session, job: ClaimedJob) -> None:
    days = refresh_keyword_daily(db)
    keywords = refresh_trends(db)
    logger.info("trends: %s keyword-day rows, %s keywords in the last 24h", days, keywords)


def handle_local_classifier_eval(db: Session, job: ClaimedJob) -> None:
    status = local_classifier.evaluate(db)
    logger.info("local classifier: %s", status)


def handle_youtube_stats(db: Session, job: ClaimedJob) -> None:
    updated = youtube_stats.refresh(db)
    if updated:
        logger.info("youtube stats: refreshed %s videos", updated)


def handle_cleanup(db: Session, job: ClaimedJob) -> None:
    now = _now()
    cutoff = now - timedelta(days=settings.ARTICLE_RETENTION_DAYS)
    old = db.execute(select(Item.id, Item.cluster_id).where(Item.published_at < cutoff)).all()
    if old:
        cluster_ids = {c for _, c in old if c is not None}
        db.execute(delete(Item).where(Item.id.in_([i for i, _ in old])))
        db.flush()
        for cluster_id in cluster_ids:
            cluster = db.get(ItemCluster, cluster_id)
            if cluster is None:
                continue
            remaining = db.execute(select(Item.id).where(Item.cluster_id == cluster_id).limit(1)).first()
            if remaining is None:
                db.delete(cluster)
            else:
                elect_primary(db, cluster)

    raw_removed = raw_store.delete_older_than(settings.RAW_RETENTION_DAYS)
    runs = db.execute(
        delete(FetchRun).where(FetchRun.started_at < now - timedelta(days=settings.FETCH_RUN_RETENTION_DAYS))
    ).rowcount
    done_jobs = db.execute(
        delete(Job).where(
            Job.status == JobStatus.DONE, Job.finished_at < now - timedelta(days=settings.JOB_DONE_RETENTION_DAYS)
        )
    ).rowcount
    dead_jobs = db.execute(
        delete(Job).where(
            Job.status == JobStatus.DEAD, Job.finished_at < now - timedelta(days=settings.JOB_DEAD_RETENTION_DAYS)
        )
    ).rowcount
    deliveries = db.execute(delete(Delivery).where(Delivery.created_at < now - timedelta(days=90))).rowcount
    stats_cutoff = (now - timedelta(days=settings.KEYWORD_STATS_RETENTION_DAYS)).date()
    db.execute(delete(KeywordDaily).where(KeywordDaily.day < stats_cutoff))
    db.execute(delete(SearchQueryDaily).where(SearchQueryDaily.day < stats_cutoff))
    logger.info(
        "cleanup: %s items, %s raw day-dirs, %s fetch_runs, %s done + %s dead jobs, %s deliveries removed",
        len(old), raw_removed, runs, done_jobs, dead_jobs, deliveries,
    )


def handle_reconcile(db: Session, job: ClaimedJob) -> None:
    """Every non-terminal item must have an active job for its next step.
    Finds the ones that don't (migrated rows, a crash between unrelated
    commits, a job that died more than DEAD_JOB_RETRY_HOURS ago) and
    enqueues it again."""
    stuck = db.execute(
        select(Item)
        .where(
            Item.status.notin_(ItemStatus.TERMINAL),
            Item.updated_at < _now() - timedelta(minutes=STUCK_AFTER_MINUTES),
        )
        .order_by(Item.published_at.desc())
        .limit(1000)
    ).scalars().all()
    if not stuck:
        return

    keys = {}
    for item in stuck:
        step = next_step(item)
        if step is not None:
            keys[dedupe_key(step[1], item.id)] = item
    covered = set(
        db.execute(
            text(
                """
                SELECT dedupe_key FROM jobs
                WHERE dedupe_key = ANY(:keys)
                  AND (status IN ('queued', 'running')
                       OR (status = 'dead' AND finished_at > now() - make_interval(hours => :hours)))
                """
            ),
            {"keys": list(keys), "hours": DEAD_JOB_RETRY_HOURS},
        ).scalars()
    )
    requeued = 0
    for key, item in keys.items():
        if key not in covered and enqueue_next(db, item) is not None:
            requeued += 1
    if requeued:
        logger.info("reconcile: re-enqueued the next step for %s stuck items", requeued)
