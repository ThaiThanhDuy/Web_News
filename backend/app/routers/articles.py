"""Public feed API. Reads items + their latest enrichments; the response
shape (ArticleOut) is unchanged from the pre-pipeline API."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import Enrichment, Item, ItemStatus, Source, Topic
from app.schemas import ArticleOut, ArticlePage, CategoryOut, SourceOut

router = APIRouter(prefix="/api/articles", tags=["articles"])


def _visible(stmt: Select) -> Select:
    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ARTICLE_RETENTION_DAYS)
    return stmt.where(
        Item.status == ItemStatus.ENRICHED,
        Item.is_duplicate.is_(False),
        Item.published_at >= retention_cutoff,
    )


def _filtered(stmt: Select, category: str | None, source: str | None) -> Select:
    if category:
        stmt = stmt.join(Topic, Topic.id == Item.primary_topic_id).where(Topic.slug == category)
    if source:
        stmt = stmt.join(Source, Source.id == Item.source_id).where(Source.slug == source)
    return stmt


def _with_relations(stmt: Select) -> Select:
    return stmt.options(joinedload(Item.source), joinedload(Item.topic), joinedload(Item.cluster))


def _summaries(db: Session, item_ids: list[int]) -> dict[int, dict]:
    """Latest summarize-stage output per item, in one query."""
    if not item_ids:
        return {}
    rows = db.execute(
        select(Enrichment.item_id, Enrichment.output)
        .where(Enrichment.item_id.in_(item_ids), Enrichment.stage == "summarize")
        .order_by(Enrichment.item_id, Enrichment.created_at.desc())
        .distinct(Enrichment.item_id)
    ).all()
    return {item_id: output for item_id, output in rows}


def _to_out(items: list[Item], db: Session) -> list[ArticleOut]:
    summaries = _summaries(db, [i.id for i in items])
    result = []
    for item in items:
        summary = summaries.get(item.id, {})
        result.append(
            ArticleOut(
                id=item.id,
                title=item.title,
                original_url=item.url,
                thumbnail_url=item.thumbnail_url,
                published_at=item.published_at,
                source=SourceOut.model_validate(item.source),
                category=CategoryOut.model_validate(item.topic) if item.topic else None,
                summary_bullets=summary.get("summary_bullets"),
                one_line_takeaway=summary.get("one_line_takeaway"),
                keywords=summary.get("keywords"),
                sentiment=item.sentiment if item.sentiment in ("positive", "neutral", "negative") else None,
                hotness_score=item.hotness_score,
                cross_source_count=item.cluster.source_count if item.cluster else 1,
            )
        )
    return result


def _feed_page(db: Session, base_stmt: Select, page: int, page_size: int) -> list[Item]:
    """The FEED_HOT_COUNT hottest items of the last FEED_HOT_WINDOW_HOURS
    lead the feed, then everything else newest-first, with no duplicates or
    gaps across pages."""
    window_start = datetime.now(timezone.utc) - timedelta(hours=settings.FEED_HOT_WINDOW_HOURS)
    hot = list(
        db.execute(
            _with_relations(base_stmt)
            .where(Item.published_at >= window_start)
            .order_by(Item.hotness_score.desc())
            .limit(settings.FEED_HOT_COUNT)
        )
        .unique()
        .scalars()
        .all()
    )
    hot_ids = [i.id for i in hot]

    offset = (page - 1) * page_size
    selected: list[Item] = []
    if offset < len(hot):
        selected.extend(hot[offset : offset + page_size])
        remaining, latest_offset = page_size - len(selected), 0
    else:
        remaining, latest_offset = page_size, offset - len(hot)

    if remaining > 0:
        selected.extend(
            db.execute(
                _with_relations(base_stmt)
                .where(Item.id.notin_(hot_ids))
                .order_by(Item.published_at.desc())
                .offset(latest_offset)
                .limit(remaining)
            )
            .unique()
            .scalars()
            .all()
        )
    return selected


@router.get("", response_model=ArticlePage)
def list_articles(
    category: str | None = Query(None, description="Topic (category) slug"),
    source: str | None = Query(None, description="Source slug"),
    sort: Literal["latest", "hot", "feed"] = "feed",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    base_stmt = _filtered(_visible(select(Item)), category, source)
    total = db.execute(select(func.count()).select_from(base_stmt.subquery())).scalar_one()

    if sort == "feed":
        items = _feed_page(db, base_stmt, page, page_size)
    else:
        order = Item.hotness_score.desc() if sort == "hot" else Item.published_at.desc()
        items = list(
            db.execute(_with_relations(base_stmt).order_by(order).offset((page - 1) * page_size).limit(page_size))
            .unique()
            .scalars()
            .all()
        )

    return ArticlePage(
        items=_to_out(items, db), page=page, page_size=page_size, total=total, has_more=page * page_size < total
    )


@router.get("/new-count")
def new_articles_count(
    since: datetime = Query(..., description="ISO timestamp — count items published after this"),
    category: str | None = Query(None),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    stmt = _filtered(_visible(select(Item.id)).where(Item.published_at > since), category, source)
    return {"count": db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()}


@router.get("/hot", response_model=list[ArticleOut])
def hot_articles(limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    items = list(
        db.execute(_with_relations(_visible(select(Item))).order_by(Item.hotness_score.desc()).limit(limit))
        .unique()
        .scalars()
        .all()
    )
    return _to_out(items, db)
