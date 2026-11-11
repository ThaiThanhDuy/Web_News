"""Same-story clustering across sources (pgvector cosine distance), and the
choice of which item of a cluster readers see.

assign_cluster() runs in the filter stage, right after the embedding is
computed: the item joins the cluster of its nearest neighbour from a
*different* source within CLUSTER_WINDOW_HOURS if it's close enough, else
starts a new cluster.

elect_primary() picks the one visible item per cluster: among members that
finished AI enrichment, the one from the most authoritative source (lowest
`sources.priority`), earliest first on ties. Electing among *enriched*
members only means a story never disappears from the feed while a
better-ranked copy is still being processed.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Item, ItemCluster, ItemStatus, Source


def assign_cluster(db: Session, item: Item) -> ItemCluster:
    window_start = datetime.now(timezone.utc) - timedelta(hours=settings.CLUSTER_WINDOW_HOURS)
    distance = Item.embedding.cosine_distance(item.embedding).label("distance")
    row = db.execute(
        select(Item.cluster_id, distance)
        .where(
            Item.id != item.id,
            Item.source_id != item.source_id,
            Item.cluster_id.is_not(None),
            Item.embedding.is_not(None),
            Item.published_at >= window_start,
        )
        .order_by(distance)
        .limit(1)
    ).first()

    if row is not None and row.distance is not None and row.distance < settings.CLUSTER_DISTANCE_THRESHOLD:
        cluster = db.get(ItemCluster, row.cluster_id)
    else:
        cluster = ItemCluster()
        db.add(cluster)
        db.flush()

    item.cluster_id = cluster.id
    db.flush()
    refresh_source_count(db, cluster)
    return cluster


def refresh_source_count(db: Session, cluster: ItemCluster) -> None:
    cluster.source_count = max(
        1,
        db.execute(
            select(func.count(func.distinct(Item.source_id))).where(Item.cluster_id == cluster.id)
        ).scalar_one(),
    )


def best_enriched_member(db: Session, cluster_id: int, exclude_item_id: int | None = None) -> Item | None:
    stmt = (
        select(Item)
        .join(Source, Source.id == Item.source_id)
        .where(Item.cluster_id == cluster_id, Item.status == ItemStatus.ENRICHED)
        .order_by(Source.priority, Item.published_at, Item.id)
        .limit(1)
    )
    if exclude_item_id is not None:
        stmt = stmt.where(Item.id != exclude_item_id)
    return db.execute(stmt).scalars().first()


def elect_primary(db: Session, cluster: ItemCluster) -> Item | None:
    winner = best_enriched_member(db, cluster.id)
    cluster.primary_item_id = winner.id if winner else None
    members = db.execute(
        select(Item).where(Item.cluster_id == cluster.id, Item.status == ItemStatus.ENRICHED)
    ).scalars().all()
    for member in members:
        member.is_duplicate = winner is not None and member.id != winner.id
    refresh_source_count(db, cluster)
    return winner
