"""Reader engagement (part B) — anonymous counters only.

Ingest: events from /api/events become hourly per-item counters, global
per-position counters and daily search-query counts. Nothing identifies a
reader: no user id, no IP (the IP is only used, unstored, to rate limit).

Position bias: an item shown first gets clicked more just for being first.
Each impression therefore adds the typical CTR of the position it was shown
at to the item's `expected_clicks`; the item's score compares its real
clicks with that expectation:

    ratio = (clicks + 0.5·tag_clicks + push_opens + α) / (expected + α), α = 3
    E_site = clamp(0.5 + log2(ratio) / 4, 0, 1)     (0.5 = as expected)

The α prior keeps items with few impressions near 0.5. E_site only enters
ranking once the site sees ENGAGEMENT_MIN_DAILY_IMPRESSIONS a day.

YouTube videos also get E_yt from public view counts (views per hour since
publishing, log-scaled: ~3,000 views/h → 1.0). E = mean of the available.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FeedPositionStats, Item, ItemEngagementHourly, SearchQueryDaily
from app.services.trends import VN
from app.utils.text import clean_text, fold

POSITION_BUCKETS = 30
PRIOR_IMPRESSIONS = 40  # prior: 2 clicks per 40 impressions = 5% CTR
PRIOR_CLICKS = 2
ALPHA = 3
YT_REFERENCE_VIEWS_PER_HOUR = 3000


@dataclass
class Event:
    type: str  # impression | click | tag_click | push_open | search
    item_id: int | None = None
    position: int | None = None
    query: str | None = None


def _bucket(position: int | None) -> int | None:
    if position is None or position < 1:
        return None
    return min(position, POSITION_BUCKETS)


def expected_ctr(stats: dict[int, tuple[int, int]], position: int | None) -> float:
    bucket = _bucket(position)
    impressions, clicks = stats.get(bucket, (0, 0)) if bucket else (0, 0)
    return (clicks + PRIOR_CLICKS) / (impressions + PRIOR_IMPRESSIONS)


def ingest(db: Session, events: list[Event]) -> int:
    """Aggregates a batch of events into the counters. Returns how many were
    applied (unknown items are ignored)."""
    item_ids = {e.item_id for e in events if e.item_id is not None}
    known = set(db.execute(select(Item.id).where(Item.id.in_(item_ids))).scalars()) if item_ids else set()
    stats = {p: (i, c) for p, i, c in db.execute(select(FeedPositionStats.position, FeedPositionStats.impressions, FeedPositionStats.clicks))}

    hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    per_item: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    per_position: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    queries: dict[str, list] = {}
    applied = 0

    for e in events:
        if e.type == "search":
            q = clean_text(e.query or "")[:200]
            key = fold(q)[:200]
            if len(key) >= 2:
                queries.setdefault(key, [q, 0])[1] += 1
                applied += 1
            continue
        if e.item_id not in known:
            continue
        counters = per_item[e.item_id]
        bucket = _bucket(e.position)
        if e.type == "impression":
            counters["impressions"] += 1
            counters["expected_clicks"] += expected_ctr(stats, e.position)
            if bucket:
                per_position[bucket][0] += 1
        elif e.type == "click":
            counters["clicks"] += 1
            if bucket:
                per_position[bucket][1] += 1
        elif e.type == "tag_click":
            counters["tag_clicks"] += 1
        elif e.type == "push_open":
            counters["push_opens"] += 1
        else:
            continue
        applied += 1

    for item_id, c in per_item.items():
        values = {k: c.get(k, 0) for k in ("impressions", "clicks", "tag_clicks", "push_opens", "expected_clicks")}
        stmt = pg_insert(ItemEngagementHourly).values(item_id=item_id, hour=hour, **values)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["item_id", "hour"],
                set_={k: getattr(ItemEngagementHourly, k) + getattr(stmt.excluded, k) for k in values},
            )
        )
    for position, (impressions, clicks) in per_position.items():
        stmt = pg_insert(FeedPositionStats).values(position=position, impressions=impressions, clicks=clicks)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["position"],
                set_={
                    "impressions": FeedPositionStats.impressions + stmt.excluded.impressions,
                    "clicks": FeedPositionStats.clicks + stmt.excluded.clicks,
                },
            )
        )
    today: date = datetime.now(VN).date()
    for key, (display, n) in queries.items():
        stmt = pg_insert(SearchQueryDaily).values(day=today, query=key, display=display, count=n)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["day", "query"],
                set_={"count": SearchQueryDaily.count + stmt.excluded.count, "display": stmt.excluded.display},
            )
        )
    return applied


def impressions_last_24h(db: Session) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return int(
        db.execute(
            select(func.coalesce(func.sum(ItemEngagementHourly.impressions), 0)).where(ItemEngagementHourly.hour >= since)
        ).scalar_one()
    )


def site_engagement_enabled(db: Session) -> bool:
    return impressions_last_24h(db) >= settings.ENGAGEMENT_MIN_DAILY_IMPRESSIONS


def site_scores(db: Session, item_ids: list[int]) -> dict[int, float]:
    """E_site per item over ENGAGEMENT_WINDOW_HOURS (only items with data)."""
    if not item_ids:
        return {}
    since = datetime.now(timezone.utc) - timedelta(hours=settings.ENGAGEMENT_WINDOW_HOURS)
    rows = db.execute(
        select(
            ItemEngagementHourly.item_id,
            func.sum(ItemEngagementHourly.clicks),
            func.sum(ItemEngagementHourly.tag_clicks),
            func.sum(ItemEngagementHourly.push_opens),
            func.sum(ItemEngagementHourly.expected_clicks),
        )
        .where(ItemEngagementHourly.item_id.in_(item_ids), ItemEngagementHourly.hour >= since)
        .group_by(ItemEngagementHourly.item_id)
    ).all()
    scores = {}
    for item_id, clicks, tag_clicks, push_opens, expected in rows:
        weighted = (clicks or 0) + 0.5 * (tag_clicks or 0) + (push_opens or 0)
        ratio = (weighted + ALPHA) / ((expected or 0) + ALPHA)
        scores[item_id] = max(0.0, min(1.0, 0.5 + math.log2(ratio) / 4))
    return scores


def youtube_score(item: Item, now: datetime | None = None) -> float | None:
    if item.ext_views is None:
        return None
    now = now or datetime.now(timezone.utc)
    hours = max(1.0, (now - item.published_at).total_seconds() / 3600)
    per_hour = item.ext_views / hours
    return max(0.0, min(1.0, math.log10(1 + per_hour) / math.log10(1 + YT_REFERENCE_VIEWS_PER_HOUR)))


def combine(site: float | None, youtube: float | None) -> float | None:
    available = [v for v in (site, youtube) if v is not None]
    return sum(available) / len(available) if available else None
