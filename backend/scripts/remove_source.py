"""Removes a source and all of its items (enrichments, deliveries and fetch
runs cascade). Clusters that lose their visible item get a new one elected
from the remaining members; clusters left empty are deleted.

Run after removing the source from app/constants.py's SOURCES (that alone
only stops future syncing; the row would stay, and keep being fetched).

Usage (from backend/, with the venv active):
    python scripts/remove_source.py <source-slug>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Item, ItemCluster, Source  # noqa: E402
from app.services.clustering import elect_primary  # noqa: E402


def main(slug: str) -> None:
    with SessionLocal() as db:
        source = db.execute(select(Source).where(Source.slug == slug)).scalar_one_or_none()
        if source is None:
            print(f"No source with slug={slug!r} — nothing to do.")
            return
        cluster_ids = set(
            db.execute(select(Item.cluster_id).where(Item.source_id == source.id, Item.cluster_id.is_not(None))).scalars()
        )
        item_count = db.execute(select(Item.id).where(Item.source_id == source.id)).all()
        db.delete(source)
        db.flush()
        for cluster_id in cluster_ids:
            cluster = db.get(ItemCluster, cluster_id)
            if cluster is None:
                continue
            if db.execute(select(Item.id).where(Item.cluster_id == cluster_id).limit(1)).first() is None:
                db.delete(cluster)
            else:
                elect_primary(db, cluster)
        db.commit()
    print(f"Removed {slug!r}: {len(item_count)} items, {len(cluster_ids)} clusters re-checked.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/remove_source.py <source-slug>")
    main(sys.argv[1])
