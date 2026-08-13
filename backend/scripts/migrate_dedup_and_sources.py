"""One-off migration: adds the is_duplicate / primary_article_id columns,
seeds the new international sources (TechCrunch, Wired, Engadget, Mashable),
and backfills the "primary" (non-duplicate) article for every existing
cluster — the one from the highest-priority source, per SOURCE_PRIORITY.

Safe to re-run.

Usage (from backend/, with the venv active):
    python scripts/migrate_dedup_and_sources.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.constants import SOURCE_PRIORITY  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.models import Article, ArticleCluster  # noqa: E402
from app.seed import seed_sources_and_categories  # noqa: E402


def add_columns() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE articles ADD COLUMN IF NOT EXISTS is_duplicate boolean NOT NULL DEFAULT false")
        )
        conn.execute(
            text(
                "ALTER TABLE article_clusters ADD COLUMN IF NOT EXISTS primary_article_id integer "
                "REFERENCES articles(id)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_articles_is_duplicate ON articles (is_duplicate)"))
    print("Columns ensured.")


def backfill_primary_articles() -> None:
    db = SessionLocal()
    try:
        cluster_ids = [row[0] for row in db.execute(select(ArticleCluster.id)).all()]
        updated_clusters = 0
        updated_articles = 0

        for cluster_id in cluster_ids:
            members = db.execute(select(Article).where(Article.cluster_id == cluster_id)).scalars().all()
            if not members:
                continue

            winner = min(members, key=lambda a: (SOURCE_PRIORITY.get(a.source.slug, 999), a.published_at))

            cluster = db.get(ArticleCluster, cluster_id)
            if cluster.primary_article_id != winner.id:
                cluster.primary_article_id = winner.id
                updated_clusters += 1

            for member in members:
                should_be_duplicate = member.id != winner.id
                if member.is_duplicate != should_be_duplicate:
                    member.is_duplicate = should_be_duplicate
                    updated_articles += 1

        db.commit()
        print(f"Backfilled {updated_clusters} clusters, updated is_duplicate on {updated_articles} articles.")
    finally:
        db.close()


def main() -> None:
    add_columns()

    db = SessionLocal()
    try:
        seed_sources_and_categories(db)
    finally:
        db.close()
    print("Seeded sources (adds TechCrunch/Wired/Engadget/Mashable if missing).")

    backfill_primary_articles()


if __name__ == "__main__":
    main()
