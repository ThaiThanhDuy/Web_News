"""Applies FOLLOWED_TOPICS to items already in the database: classified or
enriched items in any other topic become `filtered` (reason "topic not
followed: <slug>"), and the story clusters they belonged to re-elect their
visible item. New items are handled by the pipeline itself.

Reversible: the AI output is kept; set the items back to `enriched` (or
`classified` to have them summarized) with SQL if you follow the topic again.

Usage (from backend/, with the venv active):
    python scripts/apply_followed_topics.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import or_, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Item, ItemCluster, ItemStatus, Topic  # noqa: E402
from app.services.clustering import elect_primary  # noqa: E402


def main() -> None:
    followed = settings.followed_topics
    if not followed:
        print("FOLLOWED_TOPICS is empty: every topic is followed, nothing to do.")
        return
    with SessionLocal() as db:
        items = db.execute(
            select(Item)
            .outerjoin(Topic, Topic.id == Item.primary_topic_id)
            .where(
                Item.status.in_([ItemStatus.CLASSIFIED, ItemStatus.ENRICHED]),
                or_(Topic.slug.is_(None), Topic.slug.notin_(followed)),
            )
        ).scalars().all()
        clusters = set()
        counts: dict[str, int] = {}
        for item in items:
            slug = item.topic.slug if item.topic else None
            counts[f"{item.status}:{slug}"] = counts.get(f"{item.status}:{slug}", 0) + 1
            if item.status == ItemStatus.ENRICHED and item.cluster_id:
                clusters.add(item.cluster_id)
            item.status = ItemStatus.FILTERED
            item.status_reason = f"topic not followed: {slug}"
            item.is_duplicate = False
        db.flush()
        for cluster_id in clusters:
            cluster = db.get(ItemCluster, cluster_id)
            if cluster is not None:
                elect_primary(db, cluster)
        db.commit()
    print(f"Followed topics: {', '.join(followed)}")
    print(f"Filtered {len(items)} items: {dict(sorted(counts.items()))}")


if __name__ == "__main__":
    main()
