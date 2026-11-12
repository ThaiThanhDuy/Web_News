"""Public feed API. Reads items + their latest enrichments; the response
shape (ArticleOut) is unchanged from the pre-pipeline API."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import Enrichment, Item, ItemStatus, Source, Topic, TopicItem
from app.schemas import ArticleOut, ArticlePage, CategoryOut, SourceOut

router = APIRouter(prefix="/api/articles", tags=["articles"])

# Upper bound for the per-request hot_count (the reader setting's max).
MAX_HOT_COUNT = 25


def _visible(stmt: Select) -> Select:
    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ARTICLE_RETENTION_DAYS)
    return stmt.where(
        Item.status == ItemStatus.ENRICHED,
        Item.is_duplicate.is_(False),
        Item.published_at >= retention_cutoff,
    )


Lang = Literal["vi", "en"]


def _filtered(stmt: Select, category: str | None, source: str | None, lang: str | None = None) -> Select:
    if lang:
        stmt = stmt.where(Item.language == lang)
    if category:
        # Primary or related topic (topic_items), e.g. an economy story about
        # an AI startup is listed under "ai" too.
        stmt = stmt.where(
            Item.id.in_(
                select(TopicItem.item_id).join(Topic, Topic.id == TopicItem.topic_id).where(Topic.slug == category)
            )
        )
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


def _related_topics(db: Session, item_ids: list[int]) -> dict[int, list[Topic]]:
    """Secondary (non-primary) topics per item, followed topics only."""
    if not item_ids:
        return {}
    stmt = (
        select(TopicItem.item_id, Topic)
        .join(Topic, Topic.id == TopicItem.topic_id)
        .where(TopicItem.item_id.in_(item_ids), TopicItem.is_primary.is_(False))
        .order_by(Topic.sort_order)
    )
    if settings.followed_topics:
        stmt = stmt.where(Topic.slug.in_(settings.followed_topics))
    related: dict[int, list[Topic]] = {}
    for item_id, topic in db.execute(stmt).all():
        related.setdefault(item_id, []).append(topic)
    return related


def _to_out(items: list[Item], db: Session) -> list[ArticleOut]:
    summaries = _summaries(db, [i.id for i in items])
    related = _related_topics(db, [i.id for i in items])
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
                related_categories=[CategoryOut.model_validate(t) for t in related.get(item.id, [])],
                summary_bullets=summary.get("summary_bullets"),
                one_line_takeaway=summary.get("one_line_takeaway"),
                keywords=summary.get("keywords"),
                sentiment=item.sentiment if item.sentiment in ("positive", "neutral", "negative") else None,
                hotness_score=item.hotness_score,
                cross_source_count=item.cluster.source_count if item.cluster else 1,
            )
        )
    return result


# Personalization (part C): the reader's interest profile lives in their
# browser and is sent with the request; the server never stores it.
MAX_INTEREST_TOPICS = 8
MAX_INTEREST_TAGS = 20
PERSONAL_POOL = 60
PERSONAL_BOOST = 0.6


def _parse_weights(raw: str | None, limit: int) -> dict[str, float]:
    """"a:0.8,b:0.3" -> {"a": 0.8, "b": 0.3} (weights clamped to 0..1)."""
    weights: dict[str, float] = {}
    for part in (raw or "").split(",")[:limit]:
        key, _, value = part.partition(":")
        key = key.strip().lower()[:200]
        try:
            weight = max(0.0, min(1.0, float(value)))
        except ValueError:
            continue
        if key and weight > 0:
            weights[key] = weight
    return weights


def _interest_boost(item: Item, topics: dict[str, float], tags: dict[str, float]) -> float:
    topic_w = topics.get(item.topic.slug, 0.0) if item.topic else 0.0
    tag_w = max((tags.get(t, 0.0) for t in (item.tags or "").split("|") if t), default=0.0)
    return PERSONAL_BOOST * (topic_w + tag_w)


def _feed_page(
    db: Session,
    base_stmt: Select,
    page: int,
    page_size: int,
    hot_count: int,
    topics: dict[str, float] | None = None,
    tags: dict[str, float] | None = None,
) -> tuple[list[Item], set[int], set[int]]:
    """The `hot_count` hottest items of the last FEED_HOT_WINDOW_HOURS lead
    the feed, then everything else newest-first, with no duplicates or gaps
    across pages. With an interest profile, the hot pick is re-ranked by
    hotness × (1 + boost) over a wider pool. Returns (items, featured ids,
    ids featured thanks to the profile)."""
    window_start = datetime.now(timezone.utc) - timedelta(hours=settings.FEED_HOT_WINDOW_HOURS)
    personal = bool(topics or tags)
    hot: list[Item] = []
    personalized: set[int] = set()
    if hot_count > 0:
        pool = list(
            db.execute(
                _with_relations(base_stmt)
                .where(Item.published_at >= window_start)
                .order_by(Item.hotness_score.desc())
                .limit(max(hot_count, PERSONAL_POOL) if personal else hot_count)
            )
            .unique()
            .scalars()
            .all()
        )
        if personal:
            boosts = {i.id: _interest_boost(i, topics or {}, tags or {}) for i in pool}
            pool.sort(key=lambda i: i.hotness_score * (1 + boosts[i.id]), reverse=True)
            hot = pool[:hot_count]
            personalized = {i.id for i in hot if boosts[i.id] > 0}
        else:
            hot = pool
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
                .where(Item.id.notin_(hot_ids or [-1]))
                .order_by(Item.published_at.desc())
                .offset(latest_offset)
                .limit(remaining)
            )
            .unique()
            .scalars()
            .all()
        )
    return selected, set(hot_ids), personalized


@router.get("", response_model=ArticlePage)
def list_articles(
    category: str | None = Query(None, description="Topic (category) slug"),
    source: str | None = Query(None, description="Source slug"),
    sort: Literal["latest", "hot", "feed"] = "feed",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    hot_count: int | None = Query(
        None, ge=0, le=MAX_HOT_COUNT, description="sort=feed: how many hottest items lead (default FEED_HOT_COUNT)"
    ),
    lang: Lang | None = Query(None, description="Only items in this language (omit = all languages)"),
    for_topics: str | None = Query(None, max_length=600, description="Interest profile: topic:weight,..."),
    for_tags: str | None = Query(None, max_length=2000, description="Interest profile: folded-tag:weight,..."),
    db: Session = Depends(get_db),
):
    base_stmt = _filtered(_visible(select(Item)), category, source, lang)
    total = db.execute(select(func.count()).select_from(base_stmt.subquery())).scalar_one()

    featured: set[int] = set()
    personalized: set[int] = set()
    if sort == "feed":
        items, featured, personalized = _feed_page(
            db,
            base_stmt,
            page,
            page_size,
            settings.FEED_HOT_COUNT if hot_count is None else hot_count,
            _parse_weights(for_topics, MAX_INTEREST_TOPICS),
            _parse_weights(for_tags, MAX_INTEREST_TAGS),
        )
    else:
        order = Item.hotness_score.desc() if sort == "hot" else Item.published_at.desc()
        items = list(
            db.execute(_with_relations(base_stmt).order_by(order).offset((page - 1) * page_size).limit(page_size))
            .unique()
            .scalars()
            .all()
        )

    out = _to_out(items, db)
    for article in out:
        article.is_featured = article.id in featured
        article.is_personalized = article.id in personalized
    return ArticlePage(items=out, page=page, page_size=page_size, total=total, has_more=page * page_size < total)


@router.get("/new-count")
def new_articles_count(
    since: datetime = Query(..., description="ISO timestamp — count items published after this"),
    category: str | None = Query(None),
    source: str | None = Query(None),
    lang: Lang | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    stmt = _filtered(_visible(select(Item.id)).where(Item.published_at > since), category, source, lang)
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
