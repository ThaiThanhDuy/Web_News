from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    homepage_url: Mapped[str] = mapped_column(String(255))
    logo_url: Mapped[str] = mapped_column(String(500))
    rss_url: Mapped[str] = mapped_column(String(500))

    articles: Mapped[list["Article"]] = relationship(back_populates="source")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))

    articles: Mapped[list["Article"]] = relationship(back_populates="category")


class ArticleCluster(Base):
    """Groups articles from different sources that cover the same topic."""

    __tablename__ = "article_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    # The one article in this cluster that's actually shown to readers —
    # from the highest-priority source (see SOURCE_PRIORITY). Nullable +
    # no FK ondelete because Article.cluster_id already references this row;
    # the app keeps both sides in sync (see services/clustering.py).
    primary_article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    articles: Mapped[list["Article"]] = relationship(back_populates="cluster", foreign_keys="Article.cluster_id")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("article_clusters.id"), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(500))
    original_url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- AI-generated fields ---
    summary_bullets: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    one_line_takeaway: Mapped[str | None] = mapped_column(String(500), nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # positive | neutral | negative
    ai_hotness_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100, from LLM

    embedding: Mapped[list | None] = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=True)

    # --- computed ranking field ---
    hotness_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    processing_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    # True when a different, higher-priority source already covers this same
    # story (see SOURCE_PRIORITY + services/clustering.py). Excluded from
    # every public listing.
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    source: Mapped["Source"] = relationship(back_populates="articles")
    category: Mapped["Category | None"] = relationship(back_populates="articles")
    cluster: Mapped["ArticleCluster | None"] = relationship(back_populates="articles", foreign_keys=[cluster_id])
