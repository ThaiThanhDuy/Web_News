from celery import Celery

from app.config import settings

celery_app = Celery(
    "web_news",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "scrape-all-sources": {
        "task": "app.worker.tasks.scrape_all_sources",
        "schedule": settings.SCRAPE_INTERVAL_SECONDS,
    },
    "backfill-recent-articles": {
        "task": "app.worker.tasks.backfill_recent_articles",
        "schedule": settings.BACKFILL_INTERVAL_SECONDS,
    },
    "recompute-hotness-scores": {
        "task": "app.worker.tasks.recompute_hotness_scores",
        "schedule": settings.HOTNESS_RECOMPUTE_INTERVAL_SECONDS,
    },
    "cleanup-old-articles": {
        "task": "app.worker.tasks.cleanup_old_articles",
        "schedule": settings.CLEANUP_INTERVAL_SECONDS,
    },
}
