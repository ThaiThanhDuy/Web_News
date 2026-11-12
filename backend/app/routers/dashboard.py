"""Operations dashboard API (read-only): what was collected, what is being
processed, what got published, per source and per queue.

  GET /api/dashboard/summary   counts, 24h timeline, sources, queues, AI tokens
  GET /api/dashboard/items     item list filtered by group / source / title

No authentication yet (accounts are phase 6): disable with
DASHBOARD_ENABLED=false on any deployment reachable by others.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.orm import Session, joinedload

from app.ai import budget
from app.services import local_classifier
from app.config import settings
from app.database import get_db
from app.models import Item, ItemEngagementHourly, ItemStatus, KeywordTrend, SearchQueryDaily, Source

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

Group = Literal["all", "processing", "published", "duplicate", "filtered", "failed"]

PROCESSING = (
    ItemStatus.DISCOVERED,
    ItemStatus.FETCHED,
    ItemStatus.PARSED,
    ItemStatus.READY,
    ItemStatus.CLASSIFIED,
)
STAGE_ORDER = [*PROCESSING, ItemStatus.ENRICHED, ItemStatus.DUPLICATE, ItemStatus.FILTERED, ItemStatus.FAILED]


def _enabled() -> None:
    if not settings.DASHBOARD_ENABLED:
        raise HTTPException(404, "dashboard disabled")


def _retention_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=settings.ARTICLE_RETENTION_DAYS)


def _group_condition(group: Group):
    published = and_(
        Item.status == ItemStatus.ENRICHED, Item.is_duplicate.is_(False), Item.published_at >= _retention_cutoff()
    )
    return {
        "all": None,
        "processing": Item.status.in_(PROCESSING),
        "published": published,
        "duplicate": or_(
            Item.status == ItemStatus.DUPLICATE, and_(Item.status == ItemStatus.ENRICHED, Item.is_duplicate.is_(True))
        ),
        "filtered": Item.status == ItemStatus.FILTERED,
        "failed": Item.status == ItemStatus.FAILED,
    }[group]


def _group_of(item: Item) -> str:
    if item.status in PROCESSING:
        return "processing"
    if item.status == ItemStatus.ENRICHED:
        return "duplicate" if item.is_duplicate else "published"
    return {ItemStatus.DUPLICATE: "duplicate", ItemStatus.FILTERED: "filtered", ItemStatus.FAILED: "failed"}.get(
        item.status, "processing"
    )


# ----------------------------------------------------------------- summary


class Totals(BaseModel):
    collected: int
    processing: int
    published: int
    duplicate: int
    filtered: int
    failed: int
    collected_24h: int
    published_24h: int


class StageCount(BaseModel):
    status: str
    count: int


class TimelinePoint(BaseModel):
    hour: datetime
    collected: int
    published: int


class SourceRow(BaseModel):
    slug: str
    name: str
    is_active: bool
    paused: bool
    collected: int
    processing: int
    published: int
    duplicate: int
    filtered: int
    failed: int
    last_fetch_at: datetime | None
    last_success_at: datetime | None
    next_run_at: datetime | None
    consecutive_failures: int
    last_error: str | None


class QueueRow(BaseModel):
    queue: str
    due: int
    scheduled: int
    running: int
    done_1h: int
    dead: int
    oldest_due_seconds: float | None


class TokenRow(BaseModel):
    model: str
    stages: list[str]
    used: int
    cap: int


class TrendRow(BaseModel):
    keyword: str
    recent_24h: int
    sources_24h: int
    baseline_daily: float
    lift: float
    heat: float


class SearchRow(BaseModel):
    query: str
    count: int


class ClickedRow(BaseModel):
    id: int
    title: str
    url: str
    impressions: int
    clicks: int


class EngagementSummary(BaseModel):
    impressions_24h: int
    clicks_24h: int
    tag_clicks_24h: int
    push_opens_24h: int
    searches_24h: int
    in_ranking: bool
    min_daily_impressions: int
    top_clicked: list[ClickedRow]


class Summary(BaseModel):
    generated_at: datetime
    totals: Totals
    stages: list[StageCount]
    timeline: list[TimelinePoint]
    sources: list[SourceRow]
    queues: list[QueueRow]
    tokens: list[TokenRow]
    provider: str
    trends: list[TrendRow]
    top_searches: list[SearchRow]
    engagement: EngagementSummary
    local_classifier: dict


@router.get("/summary", response_model=Summary, dependencies=[Depends(_enabled)])
def summary(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    def count(cond=None) -> int:
        stmt = select(func.count()).select_from(Item)
        if cond is not None:
            stmt = stmt.where(cond)
        return db.execute(stmt).scalar_one()

    published_cond = _group_condition("published")
    totals = Totals(
        collected=count(),
        processing=count(_group_condition("processing")),
        published=count(published_cond),
        duplicate=count(_group_condition("duplicate")),
        filtered=count(_group_condition("filtered")),
        failed=count(_group_condition("failed")),
        collected_24h=count(Item.discovered_at >= day_ago),
        published_24h=count(and_(published_cond, Item.enriched_at >= day_ago)),
    )

    by_status = dict(db.execute(select(Item.status, func.count()).group_by(Item.status)).all())
    stages = [StageCount(status=s, count=by_status.get(s, 0)) for s in STAGE_ORDER]

    timeline_rows = db.execute(
        text(
            """
            WITH hours AS (
                SELECT generate_series(date_trunc('hour', now()) - interval '23 hours',
                                       date_trunc('hour', now()), interval '1 hour') AS hour
            )
            SELECT h.hour,
                   (SELECT count(*) FROM items i
                    WHERE i.discovered_at >= h.hour AND i.discovered_at < h.hour + interval '1 hour') AS collected,
                   (SELECT count(*) FROM items i
                    WHERE i.status = 'enriched' AND NOT i.is_duplicate
                      AND i.enriched_at >= h.hour AND i.enriched_at < h.hour + interval '1 hour') AS published
            FROM hours h ORDER BY h.hour
            """
        )
    ).all()
    timeline = [TimelinePoint(hour=r.hour, collected=r.collected, published=r.published) for r in timeline_rows]

    def per_source(cond):
        stmt = select(Item.source_id, func.count()).group_by(Item.source_id)
        if cond is not None:
            stmt = stmt.where(cond)
        return dict(db.execute(stmt).all())

    counts = {g: per_source(_group_condition(g)) for g in ("all", "processing", "published", "duplicate", "filtered", "failed")}
    sources = [
        SourceRow(
            slug=s.slug,
            name=s.name,
            is_active=s.is_active,
            paused=bool(s.paused_until and s.paused_until > now),
            collected=counts["all"].get(s.id, 0),
            processing=counts["processing"].get(s.id, 0),
            published=counts["published"].get(s.id, 0),
            duplicate=counts["duplicate"].get(s.id, 0),
            filtered=counts["filtered"].get(s.id, 0),
            failed=counts["failed"].get(s.id, 0),
            last_fetch_at=s.last_fetch_at,
            last_success_at=s.last_success_at,
            next_run_at=s.next_run_at,
            consecutive_failures=s.consecutive_failures,
            last_error=s.last_error,
        )
        for s in db.execute(select(Source).order_by(Source.priority)).scalars()
    ]

    queue_rows = db.execute(
        text(
            """
            SELECT queue,
                   count(*) FILTER (WHERE status = 'queued' AND run_at <= now()) AS due,
                   count(*) FILTER (WHERE status = 'queued' AND run_at > now()) AS scheduled,
                   count(*) FILTER (WHERE status = 'running') AS running,
                   count(*) FILTER (WHERE status = 'done' AND finished_at > now() - interval '1 hour') AS done_1h,
                   count(*) FILTER (WHERE status = 'dead') AS dead,
                   extract(epoch FROM now() - min(run_at) FILTER (WHERE status = 'queued' AND run_at <= now()))
                       AS oldest_due_seconds
            FROM jobs GROUP BY queue
            """
        )
    ).all()
    by_queue = {r.queue: r for r in queue_rows}
    from app.jobs.queue import QUEUES

    queues = [
        QueueRow(
            queue=q,
            due=getattr(by_queue.get(q), "due", 0) or 0,
            scheduled=getattr(by_queue.get(q), "scheduled", 0) or 0,
            running=getattr(by_queue.get(q), "running", 0) or 0,
            done_1h=getattr(by_queue.get(q), "done_1h", 0) or 0,
            dead=getattr(by_queue.get(q), "dead", 0) or 0,
            oldest_due_seconds=float(by_queue[q].oldest_due_seconds)
            if q in by_queue and by_queue[q].oldest_due_seconds is not None
            else None,
        )
        for q in QUEUES
    ]

    tokens: list[TokenRow] = []
    provider = settings.LLM_PROVIDER.strip().lower()
    if provider == "groq":
        stages_by_model: dict[str, list[str]] = {}
        stages_by_model.setdefault(settings.CLASSIFY_MODEL, []).append("phân loại")
        stages_by_model.setdefault(settings.SUMMARIZE_MODEL, []).append("tóm tắt")
        for topic, model in settings.summarize_model_by_topic.items():
            stages_by_model.setdefault(model, []).append(f"tóm tắt ({topic})")
        for model in settings.groq_fallback_models:
            stages_by_model.setdefault(model, []).append("dự phòng")
        try:
            tokens = [
                TokenRow(model=m, stages=st, used=budget.used_today(m), cap=settings.GROQ_DAILY_TOKEN_CAP)
                for m, st in stages_by_model.items()
            ]
        except Exception:  # Redis down: the rest of the dashboard still works
            tokens = []

    trends = [
        TrendRow(
            keyword=t.display,
            recent_24h=t.recent_24h,
            sources_24h=t.sources_24h,
            baseline_daily=t.baseline_daily,
            lift=t.lift,
            heat=t.heat,
        )
        for t in db.execute(
            select(KeywordTrend)
            .where(KeywordTrend.heat > 0)
            .order_by(KeywordTrend.heat.desc(), KeywordTrend.recent_24h.desc())
            .limit(10)
        ).scalars()
    ]

    week_ago = (now - timedelta(days=7)).date()
    top_searches = [
        SearchRow(query=display, count=total)
        for display, total in db.execute(
            select(func.max(SearchQueryDaily.display), func.sum(SearchQueryDaily.count).label("total"))
            .where(SearchQueryDaily.day >= week_ago)
            .group_by(SearchQueryDaily.query)
            .order_by(text("total DESC"))
            .limit(10)
        ).all()
    ]

    sums = db.execute(
        select(
            func.coalesce(func.sum(ItemEngagementHourly.impressions), 0),
            func.coalesce(func.sum(ItemEngagementHourly.clicks), 0),
            func.coalesce(func.sum(ItemEngagementHourly.tag_clicks), 0),
            func.coalesce(func.sum(ItemEngagementHourly.push_opens), 0),
        ).where(ItemEngagementHourly.hour >= day_ago)
    ).one()
    searches_24h = db.execute(
        select(func.coalesce(func.sum(SearchQueryDaily.count), 0)).where(SearchQueryDaily.day >= (now - timedelta(days=1)).date())
    ).scalar_one()
    top_clicked = [
        ClickedRow(id=r.id, title=r.title, url=r.url, impressions=r.impressions, clicks=r.clicks)
        for r in db.execute(
            select(
                Item.id,
                Item.title,
                Item.url,
                func.sum(ItemEngagementHourly.impressions).label("impressions"),
                func.sum(ItemEngagementHourly.clicks).label("clicks"),
            )
            .join(ItemEngagementHourly, ItemEngagementHourly.item_id == Item.id)
            .where(ItemEngagementHourly.hour >= day_ago)
            .group_by(Item.id)
            .having(func.sum(ItemEngagementHourly.clicks) > 0)
            .order_by(text("clicks DESC"))
            .limit(5)
        ).all()
    ]
    engagement_summary = EngagementSummary(
        impressions_24h=int(sums[0]),
        clicks_24h=int(sums[1]),
        tag_clicks_24h=int(sums[2]),
        push_opens_24h=int(sums[3]),
        searches_24h=int(searches_24h),
        in_ranking=int(sums[0]) >= settings.ENGAGEMENT_MIN_DAILY_IMPRESSIONS,
        min_daily_impressions=settings.ENGAGEMENT_MIN_DAILY_IMPRESSIONS,
        top_clicked=top_clicked,
    )

    return Summary(
        generated_at=now,
        totals=totals,
        stages=stages,
        timeline=timeline,
        sources=sources,
        queues=queues,
        tokens=tokens,
        provider=provider,
        trends=trends,
        top_searches=top_searches,
        engagement=engagement_summary,
        local_classifier=local_classifier.gate_status(),
    )


# ------------------------------------------------------------------- items


class ItemRow(BaseModel):
    id: int
    title: str
    url: str
    source_slug: str
    source_name: str
    status: str
    group: str
    status_reason: str | None
    topic: str | None
    relevance: float | None
    item_type: str
    discovered_at: datetime
    published_at: datetime
    enriched_at: datetime | None


class ItemPage(BaseModel):
    items: list[ItemRow]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]


@router.get("/items", response_model=ItemPage, dependencies=[Depends(_enabled)])
def items(
    group: Group = "all",
    source: str | None = Query(None),
    q: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []
    if source:
        filters.append(Item.source_id == select(Source.id).where(Source.slug == source).scalar_subquery())
    if q and q.strip():
        filters.append(Item.title.ilike(f"%{q.strip()}%"))

    def count(g: Group) -> int:
        stmt = select(func.count()).select_from(Item).where(*filters)
        cond = _group_condition(g)
        if cond is not None:
            stmt = stmt.where(cond)
        return db.execute(stmt).scalar_one()

    # Tab badges reflect the source/title filters too.
    counts = {g: count(g) for g in ("all", "processing", "published", "duplicate", "filtered", "failed")}

    stmt = select(Item).options(joinedload(Item.source), joinedload(Item.topic)).where(*filters)
    cond = _group_condition(group)
    if cond is not None:
        stmt = stmt.where(cond)
    # Most recently touched first: freshly collected and freshly published
    # items both surface at the top.
    order_key = case((Item.enriched_at.is_not(None), Item.enriched_at), else_=Item.discovered_at)
    rows = db.execute(stmt.order_by(order_key.desc(), Item.id.desc()).offset((page - 1) * page_size).limit(page_size))
    result = [
        ItemRow(
            id=i.id,
            title=i.title,
            url=i.url,
            source_slug=i.source.slug,
            source_name=i.source.name,
            status=i.status,
            group=_group_of(i),
            status_reason=i.status_reason,
            topic=i.topic.name if i.topic else None,
            relevance=i.relevance,
            item_type=i.item_type,
            discovered_at=i.discovered_at,
            published_at=i.published_at,
            enriched_at=i.enriched_at,
        )
        for i in rows.unique().scalars()
    ]
    return ItemPage(items=result, total=counts[group], page=page, page_size=page_size, counts=counts)
