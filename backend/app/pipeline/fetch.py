"""fetch queue: `fetch.source` (connector → new items) and `fetch.item`
(article page → clean text + raw file)."""

import logging
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors import get_connector
from app.connectors.article_page import fetch_article_page
from app.connectors.http import BlockedError
from app.jobs.queue import ClaimedJob
from app.models import FetchRun, Item, ItemStatus, Source
from app.pipeline.steps import enqueue_next
from app.services import raw_store

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_failure(
    db: Session, source: Source, run: FetchRun, status: str, error: str, http_status: int | None, retry_after: float | None
) -> None:
    now = _now()
    source.consecutive_failures += 1
    source.last_fetch_at = now
    source.last_error = error[:2000]
    backoff_minutes = min(source.fetch_interval_minutes * 2 ** source.consecutive_failures, 24 * 60)
    if retry_after:
        backoff_minutes = max(backoff_minutes, retry_after / 60)
    source.next_run_at = now + timedelta(minutes=backoff_minutes)
    if source.consecutive_failures >= settings.SOURCE_MAX_CONSECUTIVE_FAILURES:
        source.paused_until = now + timedelta(hours=settings.SOURCE_PAUSE_HOURS)
        logger.error(
            "Source %s paused for %sh after %s consecutive failures: %s",
            source.slug, settings.SOURCE_PAUSE_HOURS, source.consecutive_failures, error,
        )
    else:
        logger.warning("Source %s fetch %s (%s in a row): %s", source.slug, status, source.consecutive_failures, error)
    run.status = status
    run.http_status = http_status
    run.error = error[:4000]
    run.finished_at = now
    db.add(run)


def handle_fetch_source(db: Session, job: ClaimedJob) -> None:
    source = db.get(Source, job.payload["source_id"])
    if source is None or not source.is_active:
        return
    connector = get_connector(source.connector)
    run = FetchRun(source_id=source.id, status="error", started_at=_now())

    try:
        result = connector.fetch(source, dict(source.cursor or {}))
    except BlockedError as exc:
        _record_failure(db, source, run, "blocked", str(exc), exc.http_status, exc.retry_after)
        return
    except (requests.RequestException, ValueError) as exc:
        status = exc.response.status_code if getattr(exc, "response", None) is not None else None
        _record_failure(db, source, run, "error", f"{type(exc).__name__}: {exc}", status, None)
        return

    health = connector.health(result)
    if not health.ok:
        # e.g. HTTP 202 with an empty body (bot protection): counts as a
        # failed fetch, so a source that keeps doing it gets paused, and the
        # cursor is not advanced.
        _record_failure(db, source, run, "error", health.message, result.http_status, None)
        return

    now = _now()
    cutoff = now - timedelta(days=settings.ARTICLE_RETENTION_DAYS)
    new_items = 0
    for found in result.items:
        if found.published_at < cutoff:
            continue  # would be deleted by retention right away
        item_id = db.execute(
            pg_insert(Item)
            .values(
                source_id=source.id,
                item_type=source.item_type,
                external_id=found.external_id[:1000],
                url=found.url[:1000],
                title=found.title[:500],
                thumbnail_url=found.thumbnail_url if found.thumbnail_url and len(found.thumbnail_url) <= 1000 else None,
                published_at=found.published_at,
                feed_summary=found.summary,
                status=ItemStatus.DISCOVERED,
            )
            .on_conflict_do_nothing(constraint="uq_items_source_external")
            .returning(Item.id)
        ).scalar_one_or_none()
        if item_id is None:
            continue
        new_items += 1
        item = db.get(Item, item_id)
        if source.item_type == "video":
            # No page to fetch: the feed entry is the whole document.
            item.raw_path = raw_store.save(
                source.connector,
                source.id,
                {"url": found.url, "fetched_at": now, "title": found.title, "text": found.summary},
            )
        enqueue_next(db, item)

    # The cursor only advances now, in the same transaction as the items.
    source.cursor = result.cursor
    source.consecutive_failures = 0
    source.paused_until = None
    source.last_error = None
    source.last_fetch_at = now
    source.last_success_at = now
    run.status = "not_modified" if result.not_modified else "ok"
    run.http_status = result.http_status
    run.items_seen = len(result.items)
    run.items_new = new_items
    run.finished_at = now
    db.add(run)
    if new_items:
        logger.info("Source %s: %s new items (%s in feed)", source.slug, new_items, len(result.items))


def handle_fetch_item(db: Session, job: ClaimedJob) -> None:
    item = db.get(Item, job.payload["item_id"])
    if item is None or item.status != ItemStatus.DISCOVERED:
        return  # already handled (idempotent re-run)

    page = None
    reason = None
    try:
        page = fetch_article_page(item.url)
    except BlockedError as exc:
        reason = f"page blocked: {exc}"
    except (requests.RequestException, ValueError) as exc:
        if not job.is_last_attempt:
            raise  # retried with backoff
        reason = f"page unavailable: {type(exc).__name__}: {exc}"

    if page is not None and page.text is None:
        reason = "no main text extracted from page"
    if reason:
        # Keep going with the feed description / title rather than losing
        # the item ("đầy đủ dữ liệu").
        logger.info("item %s: %s — using feed summary", item.id, reason)

    item.content = page.text if page is not None else None
    if page is not None and page.og_image and not item.thumbnail_url and len(page.og_image) <= 1000:
        item.thumbnail_url = page.og_image
    item.raw_path = raw_store.save(
        item.source.connector,
        item.source_id,
        {
            "item_id": item.id,
            "url": item.url,
            "final_url": page.final_url if page else None,
            "http_status": page.http_status if page else None,
            "fetched_at": _now(),
            "title": item.title,
            "text": item.content,
            "feed_summary": item.feed_summary,
            "og_image": page.og_image if page else None,
        },
    )
    item.status = ItemStatus.FETCHED
    item.status_reason = reason[:300] if reason else None
    enqueue_next(db, item)
