from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import Article, Category, Source
from app.schemas import ArticleOut, ArticlePage

router = APIRouter(prefix="/api/articles", tags=["articles"])


def _to_out(article: Article) -> ArticleOut:
    out = ArticleOut.model_validate(article)
    out.cross_source_count = article.cluster.source_count if article.cluster else 1
    return out


def _with_relations(stmt: Select) -> Select:
    return stmt.options(joinedload(Article.source), joinedload(Article.category), joinedload(Article.cluster))


def _feed_page(db: Session, base_stmt: Select, page: int, page_size: int) -> list[ArticleOut]:
    """Feed ordering: the FEED_HOT_COUNT hottest articles published within
    FEED_HOT_WINDOW_HOURS lead the feed, followed by everything else
    newest-first (with no duplicates or gaps across pages)."""
    window_start = datetime.now(timezone.utc) - timedelta(hours=settings.FEED_HOT_WINDOW_HOURS)
    hot_stmt = (
        _with_relations(base_stmt)
        .where(Article.published_at >= window_start)
        .order_by(Article.hotness_score.desc())
        .limit(settings.FEED_HOT_COUNT)
    )
    hot_articles = list(db.execute(hot_stmt).unique().scalars().all())
    hot_ids = [a.id for a in hot_articles]
    hot_count = len(hot_ids)

    offset = (page - 1) * page_size
    selected: list[Article] = []

    if offset < hot_count:
        selected.extend(hot_articles[offset : offset + page_size])
        remaining_needed = page_size - len(selected)
        latest_offset = 0
    else:
        remaining_needed = page_size
        latest_offset = offset - hot_count

    if remaining_needed > 0:
        latest_stmt = (
            _with_relations(base_stmt)
            .where(Article.id.notin_(hot_ids))
            .order_by(Article.published_at.desc())
            .offset(latest_offset)
            .limit(remaining_needed)
        )
        selected.extend(db.execute(latest_stmt).unique().scalars().all())

    return [_to_out(a) for a in selected]


@router.get("", response_model=ArticlePage)
def list_articles(
    category: str | None = Query(None, description="Category slug"),
    source: str | None = Query(None, description="Source slug"),
    sort: Literal["latest", "hot", "feed"] = "feed",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ARTICLE_RETENTION_DAYS)
    base_stmt = select(Article).where(
        Article.is_processed.is_(True),
        Article.is_duplicate.is_(False),
        Article.published_at >= retention_cutoff,
    )
    if category:
        base_stmt = base_stmt.join(Category).where(Category.slug == category)
    if source:
        base_stmt = base_stmt.join(Source).where(Source.slug == source)

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = db.execute(count_stmt).scalar_one()

    if sort == "feed":
        items = _feed_page(db, base_stmt, page, page_size)
    else:
        ordered_stmt = _with_relations(base_stmt).order_by(
            Article.hotness_score.desc() if sort == "hot" else Article.published_at.desc()
        )
        ordered_stmt = ordered_stmt.offset((page - 1) * page_size).limit(page_size)
        items = [_to_out(a) for a in db.execute(ordered_stmt).unique().scalars().all()]

    return ArticlePage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


@router.get("/new-count")
def new_articles_count(
    since: datetime = Query(..., description="ISO timestamp — count articles published after this"),
    category: str | None = Query(None, description="Category slug"),
    source: str | None = Query(None, description="Source slug"),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    stmt = select(Article.id).where(
        Article.is_processed.is_(True),
        Article.is_duplicate.is_(False),
        Article.published_at > since,
    )
    if category:
        stmt = stmt.join(Category).where(Category.slug == category)
    if source:
        stmt = stmt.join(Source).where(Source.slug == source)

    count = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    return {"count": count}


@router.get("/hot", response_model=list[ArticleOut])
def hot_articles(limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ARTICLE_RETENTION_DAYS)
    stmt = (
        _with_relations(select(Article))
        .where(
            Article.is_processed.is_(True),
            Article.is_duplicate.is_(False),
            Article.published_at >= retention_cutoff,
        )
        .order_by(Article.hotness_score.desc())
        .limit(limit)
    )
    articles = db.execute(stmt).unique().scalars().all()
    return [_to_out(a) for a in articles]
