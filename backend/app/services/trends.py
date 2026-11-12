"""Keyword trends (part A of the hot-news analytics).

1. keyword_daily — per Vietnam-time day (by publish date): how many enriched
   items mentioned each keyword, from how many sources. Recomputed for the
   last 2 days on every run (the first run backfills every day still in the
   DB); older days are frozen and kept KEYWORD_STATS_RETENTION_DAYS, long
   after the items themselves are deleted.

2. keyword_trends — for every keyword seen in the last 24h:
     lift = log2((recent_24h + 1) / (baseline_daily + 1))
     heat = clamp(lift / 3, 0, 1) · min(1, recent/3) · min(1, sources/2)
   baseline_daily = mean daily mentions over the previous TREND_BASELINE_DAYS
   (or fewer, while that much history doesn't exist yet). A keyword needs
   several mentions from more than one outlet to get hot: one site posting
   a series of promos isn't a trend.

An item's trend score K = heat of its hottest keyword.
"""

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Item, KeywordDaily, KeywordTrend
from app.utils.text import fold_tag

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _enriched_keywords(db: Session, since: datetime) -> list[tuple[int, datetime, list[str]]]:
    """(source_id, published_at, keywords) of enriched items published since."""
    rows = db.execute(
        text(
            """
            SELECT i.source_id, i.published_at, e.output -> 'keywords' AS keywords
            FROM items i
            JOIN LATERAL (
                SELECT output FROM enrichments
                WHERE item_id = i.id AND stage = 'summarize'
                ORDER BY created_at DESC LIMIT 1
            ) e ON true
            WHERE i.status = 'enriched' AND i.published_at >= :since
            """
        ),
        {"since": since},
    ).all()
    return [(r.source_id, r.published_at, [str(k) for k in (r.keywords or [])]) for r in rows]


def _aggregate(rows) -> tuple[Counter, dict[str, set], dict[str, Counter]]:
    counts: Counter[str] = Counter()
    sources: dict[str, set] = defaultdict(set)
    spellings: dict[str, Counter] = defaultdict(Counter)
    for source_id, _published, keywords in rows:
        for kw in set(keywords):
            key = fold_tag(kw)
            if not key or len(key) > 200:
                continue
            counts[key] += 1
            sources[key].add(source_id)
            spellings[key][kw.strip()[:200]] += 1
    return counts, sources, spellings


def refresh_keyword_daily(db: Session) -> int:
    today = datetime.now(VN).date()
    empty = db.execute(select(func.count()).select_from(KeywordDaily)).scalar_one() == 0
    first_day = today - timedelta(days=(settings.ARTICLE_RETENTION_DAYS if empty else 1))
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=VN)

    by_day: dict[date, list] = defaultdict(list)
    for row in _enriched_keywords(db, since):
        by_day[row[1].astimezone(VN).date()].append(row)

    db.execute(delete(KeywordDaily).where(KeywordDaily.day >= first_day))
    written = 0
    for day, rows in by_day.items():
        counts, sources, spellings = _aggregate(rows)
        for key, n in counts.items():
            db.add(
                KeywordDaily(
                    day=day,
                    keyword=key,
                    display=spellings[key].most_common(1)[0][0],
                    item_count=n,
                    source_count=len(sources[key]),
                )
            )
            written += 1
    return written


def refresh_trends(db: Session) -> int:
    now = datetime.now(timezone.utc)
    today = now.astimezone(VN).date()
    counts, sources, spellings = _aggregate(_enriched_keywords(db, now - timedelta(hours=24)))

    first_history_day = db.execute(select(func.min(KeywordDaily.day))).scalar_one()
    history_days = (today - first_history_day).days if first_history_day else 0
    baseline_days = max(1, min(settings.TREND_BASELINE_DAYS, history_days))
    baseline_from = today - timedelta(days=baseline_days)
    baseline = dict(
        db.execute(
            select(KeywordDaily.keyword, func.sum(KeywordDaily.item_count))
            .where(KeywordDaily.day >= baseline_from, KeywordDaily.day < today)
            .group_by(KeywordDaily.keyword)
        ).all()
    )

    db.execute(delete(KeywordTrend))
    for key, recent in counts.items():
        base = (baseline.get(key) or 0) / baseline_days
        lift = math.log2((recent + 1) / (base + 1))
        n_sources = len(sources[key])
        heat = max(0.0, min(1.0, lift / 3)) * min(1.0, recent / 3) * min(1.0, n_sources / 2)
        db.add(
            KeywordTrend(
                keyword=key,
                display=spellings[key].most_common(1)[0][0],
                recent_24h=recent,
                sources_24h=n_sources,
                baseline_daily=round(base, 3),
                lift=round(lift, 3),
                heat=round(heat, 4),
                updated_at=now,
            )
        )
    return len(counts)


def load_heat_map(db: Session) -> dict[str, float]:
    return dict(db.execute(select(KeywordTrend.keyword, KeywordTrend.heat).where(KeywordTrend.heat > 0)).all())


def item_tags(item: Item) -> list[str]:
    return [t for t in (item.tags or "").split("|") if t]


def item_trend(item: Item, heat_map: dict[str, float]) -> float:
    return max((heat_map.get(tag, 0.0) for tag in item_tags(item)), default=0.0)
