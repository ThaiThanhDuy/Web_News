"""Cross-source duplicate/topic clustering using pgvector cosine distance.

When a new article is processed we look for the nearest already-clustered
article from a *different* source published within the last
CLUSTER_WINDOW_HOURS. If it's close enough (cosine distance below the
threshold) we consider them the same story and reuse its cluster, otherwise
we start a new one. `ArticleCluster.source_count` (distinct sources covering
the story) is used as one of the inputs to the hotness score.

Within a cluster, only one article is shown to readers — the one from the
highest-priority source (see SOURCE_PRIORITY) — the rest are flagged
`is_duplicate` and excluded from every public listing.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import SOURCE_PRIORITY
from app.models import Article, ArticleCluster


def _priority(article: Article) -> int:
    return SOURCE_PRIORITY.get(article.source.slug, 999)


def assign_cluster(db: Session, article: Article) -> ArticleCluster:
    window_start = datetime.now(timezone.utc) - timedelta(hours=settings.CLUSTER_WINDOW_HOURS)

    stmt = (
        select(Article, Article.embedding.cosine_distance(article.embedding).label("distance"))
        .where(
            Article.id != article.id,
            Article.source_id != article.source_id,
            Article.cluster_id.is_not(None),
            Article.embedding.is_not(None),
            Article.published_at >= window_start,
        )
        .order_by("distance")
        .limit(1)
    )
    row = db.execute(stmt).first()

    if row is not None and row.distance is not None and row.distance < settings.CLUSTER_DISTANCE_THRESHOLD:
        nearest_article: Article = row[0]
        cluster = nearest_article.cluster
    else:
        cluster = ArticleCluster()
        db.add(cluster)
        db.flush()

    article.cluster_id = cluster.id
    db.flush()

    distinct_sources = db.execute(
        select(Article.source_id).where(Article.cluster_id == cluster.id).distinct()
    ).all()
    cluster.source_count = len(distinct_sources)

    _update_primary(db, cluster, article)

    return cluster


def _update_primary(db: Session, cluster: ArticleCluster, new_article: Article) -> None:
    """Keeps exactly one non-duplicate article per cluster: the one from the
    most authoritative source, per SOURCE_PRIORITY."""
    current_primary = db.get(Article, cluster.primary_article_id) if cluster.primary_article_id else None

    if current_primary is None or current_primary.id == new_article.id:
        new_article.is_duplicate = False
        cluster.primary_article_id = new_article.id
        return

    if _priority(new_article) < _priority(current_primary):
        current_primary.is_duplicate = True
        new_article.is_duplicate = False
        cluster.primary_article_id = new_article.id
    else:
        new_article.is_duplicate = True
