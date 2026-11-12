"""Puts the ranking inputs together for one or many items and stores the
cached components (trend_score K, engagement_score E) next to the score."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item, ItemCluster, KeywordTrend, Source
from app.services import engagement
from app.services.hotness import compute_hotness
from app.services.trends import item_tags, item_trend, load_heat_map


def rescore(db: Session, items: list[Item]) -> None:
    """Recomputes hotness for `items` (batch: one query per input kind)."""
    if not items:
        return
    heat_map = load_heat_map(db)
    site_on = engagement.site_engagement_enabled(db)
    site = engagement.site_scores(db, [i.id for i in items]) if site_on else {}
    trust = dict(db.execute(select(Source.id, Source.trust)).all())
    cluster_ids = {i.cluster_id for i in items if i.cluster_id}
    coverage = (
        dict(db.execute(select(ItemCluster.id, ItemCluster.source_count).where(ItemCluster.id.in_(cluster_ids))).all())
        if cluster_ids
        else {}
    )
    for item in items:
        item.trend_score = round(item_trend(item, heat_map), 4)
        e = engagement.combine(site.get(item.id), engagement.youtube_score(item))
        item.engagement_score = None if e is None else round(e, 4)
        item.hotness_score = compute_hotness(
            published_at=item.published_at,
            relevance=item.relevance,
            trust=trust.get(item.source_id),
            cluster_source_count=coverage.get(item.cluster_id, 1) if item.cluster_id else 1,
            trend=item.trend_score,
            engagement=item.engagement_score,
        )


def rescore_one(db: Session, item: Item) -> None:
    """Cheaper single-item variant used right after summarizing."""
    tags = item_tags(item)
    heat = (
        dict(db.execute(select(KeywordTrend.keyword, KeywordTrend.heat).where(KeywordTrend.keyword.in_(tags))).all())
        if tags
        else {}
    )
    item.trend_score = round(item_trend(item, heat), 4)
    item.engagement_score = None
    cluster = db.get(ItemCluster, item.cluster_id) if item.cluster_id else None
    item.hotness_score = compute_hotness(
        published_at=item.published_at,
        relevance=item.relevance,
        trust=item.source.trust,
        cluster_source_count=cluster.source_count if cluster else 1,
        trend=item.trend_score,
    )
