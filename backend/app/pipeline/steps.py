"""Item status -> the single job that advances it. Every handler calls
enqueue_next() in the same transaction that changes the status, and the
reconcile job uses the same mapping to repair anything that slipped
through (e.g. rows migrated from the old schema)."""

from sqlalchemy.orm import Session

from app.jobs.queue import enqueue, recency_priority
from app.models import Item, ItemStatus


def next_step(item: Item) -> tuple[str, str] | None:
    status = item.status
    if status == ItemStatus.DISCOVERED:
        return ("parse", "parse.item") if item.item_type == "video" else ("fetch", "fetch.item")
    if status == ItemStatus.FETCHED:
        return "parse", "parse.item"
    if status == ItemStatus.PARSED:
        return "filter", "filter.item"
    if status == ItemStatus.READY:
        return "ai_fast", "ai.classify"
    if status == ItemStatus.CLASSIFIED:
        return "ai_deep", "ai.summarize"
    return None


def dedupe_key(kind: str, item_id: int) -> str:
    return f"{kind}:{item_id}"


def enqueue_next(db: Session, item: Item) -> int | None:
    step = next_step(item)
    if step is None:
        return None
    queue, kind = step
    return enqueue(
        db,
        queue,
        kind,
        {"item_id": item.id},
        dedupe_key=dedupe_key(kind, item.id),
        priority=recency_priority(item.published_at),
    )
