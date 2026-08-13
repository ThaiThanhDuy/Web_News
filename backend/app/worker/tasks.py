import logging
from datetime import datetime, timedelta, timezone

from celery.exceptions import MaxRetriesExceededError, Retry
from sqlalchemy import select

from app.config import settings
from app.constants import SOURCE_PRIORITY, VIDEO_SOURCE_SLUGS
from app.database import SessionLocal
from app.models import Article, ArticleCluster, Category, Source
from app.scraper.content_extractor import fetch_article
from app.scraper.rss_fetcher import fetch_feed_items
from app.scraper.vietnamnet_scraper import fetch_vietnamnet_items
from app.services.clustering import assign_cluster
from app.services.embeddings import embed_text
from app.services.hotness import compute_hotness
from app.services.llm import TransientLLMError, analyze_article
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _scrape_and_ingest(min_published_at: datetime | None = None) -> list[int]:
    """Fetches every source's feed and inserts whatever isn't already in the
    database (by original_url). Shared by scrape_all_sources (every run) and
    backfill_recent_articles (a slower, redundant safety-net pass) — both
    read from the same feeds, since RSS/JSON-LD only ever expose their
    current "latest items" window, not an actual history to page through.
    min_published_at, when given, skips anything older than that instead of
    inserting it.
    """
    db = SessionLocal()
    new_article_ids: list[int] = []
    try:
        sources = db.execute(select(Source)).scalars().all()
        for source in sources:
            try:
                if source.slug == "vietnamnet":
                    items = fetch_vietnamnet_items(source.rss_url)
                else:
                    items = fetch_feed_items(source.rss_url)
            except Exception:
                logger.exception("Failed to fetch feed for source %s", source.slug)
                continue

            for item in items:
                if min_published_at is not None and item.published_at < min_published_at:
                    continue

                exists = db.execute(
                    select(Article.id).where(Article.original_url == item.url)
                ).first()
                if exists:
                    continue

                article = Article(
                    source_id=source.id,
                    title=item.title,
                    original_url=item.url,
                    thumbnail_url=item.thumbnail_url,
                    published_at=item.published_at,
                    hotness_score=0.0,
                    # For video sources there's no article page to scrape,
                    # so the RSS description is the only content available —
                    # stash it now, process_article picks it up from here.
                    raw_content=item.description if source.slug in VIDEO_SOURCE_SLUGS else None,
                )
                db.add(article)
                db.flush()
                new_article_ids.append(article.id)

        db.commit()
    finally:
        db.close()

    for article_id in new_article_ids:
        process_article.delay(article_id)

    return new_article_ids


@celery_app.task(name="app.worker.tasks.scrape_all_sources")
def scrape_all_sources() -> dict:
    return {"new_articles": len(_scrape_and_ingest())}


@celery_app.task(name="app.worker.tasks.backfill_recent_articles")
def backfill_recent_articles() -> dict:
    """Redundant, slower-cadence re-scan of every source's feed, catching
    anything the frequent scrape_all_sources run missed (a transient fetch
    failure, a brief outage, ...) before it's gone for good — sources only
    ever show their current window of latest items, so once something
    scrolls out of that, it's unrecoverable. Bounded to the last
    BACKFILL_MAX_AGE_DAYS so it doesn't try to resurrect anything already stale."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.BACKFILL_MAX_AGE_DAYS)
    return {"new_articles": len(_scrape_and_ingest(min_published_at=cutoff))}


@celery_app.task(name="app.worker.tasks.process_article", bind=True, max_retries=8, default_retry_delay=60)
def process_article(self, article_id: int) -> None:
    db = SessionLocal()
    try:
        article = db.get(Article, article_id)
        if article is None:
            return

        if article.source.slug in VIDEO_SOURCE_SLUGS:
            # Pre-filled from the RSS description in scrape_all_sources —
            # there's no article page here to run trafilatura against.
            content = article.raw_content or article.title
        else:
            content, og_image = fetch_article(article.original_url)
            if not content:
                content = article.title  # fall back to the title alone
            if not article.thumbnail_url and og_image:
                article.thumbnail_url = og_image

        try:
            analysis = analyze_article(article.title, content)
        except TransientLLMError as exc:
            db.rollback()
            raise self.retry(exc=exc, countdown=exc.retry_after or 60)

        if analysis is None:
            article.processing_failed = True
            db.commit()
            return

        category = db.execute(
            select(Category).where(Category.slug == analysis["category"])
        ).scalar_one_or_none()

        article.raw_content = content[:20000]
        article.summary_bullets = analysis["summary_bullets"]
        article.one_line_takeaway = analysis["one_line_takeaway"]
        article.keywords = analysis["keywords"]
        article.sentiment = analysis["sentiment"]
        article.ai_hotness_score = analysis["ai_hotness_score"]
        article.category_id = category.id if category else None
        article.embedding = embed_text(f"{article.title}\n{content}")

        cluster = assign_cluster(db, article)

        article.hotness_score = compute_hotness(
            published_at=article.published_at,
            cluster_source_count=cluster.source_count,
            ai_hotness_score=article.ai_hotness_score,
        )
        article.is_processed = True
        article.processing_failed = False
        db.commit()
    except Retry:
        raise  # already handled (and logged) at the raise site above
    except MaxRetriesExceededError:
        db.rollback()
        logger.error("Giving up on article %s after exhausting retries", article_id)
        article = db.get(Article, article_id)
        if article is not None:
            article.processing_failed = True
            db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to process article %s", article_id)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="app.worker.tasks.recompute_hotness_scores")
def recompute_hotness_scores() -> dict:
    """Freshness decays over time, so periodically refresh hotness_score for
    recently published, already-processed articles (cheap: no LLM/embedding calls)."""
    db = SessionLocal()
    try:
        window_start = datetime.now(timezone.utc) - timedelta(hours=settings.HOTNESS_WINDOW_HOURS)
        articles = db.execute(
            select(Article).where(
                Article.is_processed.is_(True),
                Article.is_duplicate.is_(False),
                Article.published_at >= window_start,
            )
        ).scalars().all()

        for article in articles:
            source_count = article.cluster.source_count if article.cluster else 1
            article.hotness_score = compute_hotness(
                published_at=article.published_at,
                cluster_source_count=source_count,
                ai_hotness_score=article.ai_hotness_score,
            )

        db.commit()
        return {"updated": len(articles)}
    finally:
        db.close()


@celery_app.task(name="app.worker.tasks.cleanup_old_articles")
def cleanup_old_articles() -> dict:
    """Permanently deletes articles older than ARTICLE_RETENTION_DAYS. Any
    cluster that loses its primary (non-duplicate) article this way gets a
    new one re-elected from its remaining members, per SOURCE_PRIORITY;
    clusters left with no members are deleted too."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ARTICLE_RETENTION_DAYS)
        old_articles = db.execute(select(Article).where(Article.published_at < cutoff)).scalars().all()
        if not old_articles:
            return {"deleted": 0, "clusters_promoted": 0, "clusters_removed": 0}

        delete_ids = {a.id for a in old_articles}
        affected_cluster_ids = {a.cluster_id for a in old_articles if a.cluster_id is not None}

        promoted = 0
        emptied_cluster_ids: list[int] = []

        for cluster_id in affected_cluster_ids:
            cluster = db.get(ArticleCluster, cluster_id)
            if cluster is None:
                continue

            members = db.execute(select(Article).where(Article.cluster_id == cluster_id)).scalars().all()
            remaining = [a for a in members if a.id not in delete_ids]

            if not remaining:
                cluster.primary_article_id = None
                emptied_cluster_ids.append(cluster_id)
                continue

            if cluster.primary_article_id in delete_ids:
                winner = min(remaining, key=lambda a: (SOURCE_PRIORITY.get(a.source.slug, 999), a.published_at))
                cluster.primary_article_id = winner.id
                for member in remaining:
                    member.is_duplicate = member.id != winner.id
                promoted += 1

            cluster.source_count = len({a.source_id for a in remaining})

        # Persist cluster.primary_article_id changes *before* deleting the
        # articles they used to point to, or the FK constraint rejects it.
        db.flush()

        for article in old_articles:
            db.delete(article)
        db.flush()

        for cluster_id in emptied_cluster_ids:
            cluster = db.get(ArticleCluster, cluster_id)
            if cluster is not None:
                db.delete(cluster)

        db.commit()
        logger.info(
            "cleanup_old_articles: deleted %d articles older than %d days, promoted %d clusters, removed %d empty clusters",
            len(old_articles), settings.ARTICLE_RETENTION_DAYS, promoted, len(emptied_cluster_ids),
        )
        return {"deleted": len(old_articles), "clusters_promoted": promoted, "clusters_removed": len(emptied_cluster_ids)}
    finally:
        db.close()
