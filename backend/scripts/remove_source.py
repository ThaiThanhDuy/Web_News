"""Removes a source and all of its articles from the database. If any of
those articles was the "primary" (non-duplicate) article of a cluster, a new
primary is re-elected from the cluster's remaining members per
SOURCE_PRIORITY; clusters left with no members are deleted too.

Run this after removing a source from app/constants.py's SOURCES list (that
alone only stops future scraping — it doesn't touch existing rows).

Usage (from backend/, with the venv active):
    python scripts/remove_source.py <source-slug>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.constants import SOURCE_PRIORITY  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Article, ArticleCluster, Source  # noqa: E402


def main(slug: str) -> None:
    db = SessionLocal()
    try:
        source = db.execute(select(Source).where(Source.slug == slug)).scalar_one_or_none()
        if source is None:
            print(f"No source with slug={slug!r} found — nothing to do.")
            return

        articles_to_delete = db.execute(select(Article).where(Article.source_id == source.id)).scalars().all()
        delete_ids = {a.id for a in articles_to_delete}
        affected_cluster_ids = {a.cluster_id for a in articles_to_delete if a.cluster_id is not None}

        print(f"Found {len(articles_to_delete)} articles from {slug!r} across {len(affected_cluster_ids)} clusters.")

        promoted = 0
        emptied_cluster_ids: list[int] = []

        for cluster_id in affected_cluster_ids:
            cluster = db.get(ArticleCluster, cluster_id)
            if cluster is None:
                continue

            members = db.execute(select(Article).where(Article.cluster_id == cluster_id)).scalars().all()
            remaining = [a for a in members if a.id not in delete_ids]

            if not remaining:
                cluster.primary_article_id = None
                emptied_cluster_ids.append(cluster_id)
                continue

            if cluster.primary_article_id in delete_ids:
                winner = min(remaining, key=lambda a: (SOURCE_PRIORITY.get(a.source.slug, 999), a.published_at))
                cluster.primary_article_id = winner.id
                for member in remaining:
                    member.is_duplicate = member.id != winner.id
                promoted += 1

            cluster.source_count = len({a.source_id for a in remaining})

        # Persist the cluster.primary_article_id changes *before* deleting the
        # articles they used to point to, or the FK constraint would reject it.
        db.flush()

        for article in articles_to_delete:
            db.delete(article)
        db.flush()

        for cluster_id in emptied_cluster_ids:
            cluster = db.get(ArticleCluster, cluster_id)
            if cluster is not None:
                db.delete(cluster)

        db.delete(source)
        db.commit()

        print(
            f"Done. Re-elected primary for {promoted} clusters, removed {len(emptied_cluster_ids)} "
            f"now-empty clusters, deleted source {slug!r} and its {len(articles_to_delete)} articles."
        )
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/remove_source.py <source-slug>")
        sys.exit(1)
    main(sys.argv[1])
