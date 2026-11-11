"""Database schema (PostgreSQL 15+ with pgvector). Changes go through Alembic
migrations in backend/migrations — never Base.metadata.create_all.

Groups:
  - Sources:      sources, fetch_runs
  - Content:      items, item_clusters
  - AI:           pipeline_versions, enrichments
  - Topics:       topics (Hướng 1: public categories)
  - Job pool:     jobs
  - Distribution: push_subscriptions, deliveries

Tenants/users/subscriptions/RLS (phase 6) are not part of this schema yet.
"""

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------- sources


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    homepage_url: Mapped[str] = mapped_column(String(255))
    logo_url: Mapped[str] = mapped_column(String(500))
    # One row per feed URL: the same feed is only ever crawled once.
    feed_url: Mapped[str] = mapped_column(String(500), unique=True)
    # Which connector implementation reads this source (app/connectors).
    connector: Mapped[str] = mapped_column(String(30), server_default="rss")
    item_type: Mapped[str] = mapped_column(String(20), server_default="news")  # news | video
    # Lower = more authoritative; wins when several sources cover one story.
    priority: Mapped[int] = mapped_column(Integer, server_default="100")
    # Source trust T in the ranking formula, 0..1.
    trust: Mapped[float] = mapped_column(Float, server_default="0.5")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, server_default="30")
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    # Connector state (etag, last_modified, ...). Only advanced after the
    # items of a run have been committed.
    cursor: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default="0")
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["Item"]] = relationship(back_populates="source")


class FetchRun(Base):
    __tablename__ = "fetch_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ok | not_modified | blocked | error
    status: Mapped[str] = mapped_column(String(20))
    http_status: Mapped[int | None] = mapped_column(Integer)
    items_seen: Mapped[int] = mapped_column(Integer, server_default="0")
    items_new: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)


# ------------------------------------------------------------------ topics


class Topic(Base):
    """Hướng 1: the fixed public categories. Hướng 2 will add per-tenant
    topics to this same table."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_public: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="100")


# ----------------------------------------------------------------- content


class ItemStatus:
    """Item lifecycle. Each non-terminal status has exactly one next job
    (see pipeline/maintenance.py NEXT_STEP)."""

    DISCOVERED = "discovered"  # → fetch.item (news) / parse.item (video)
    FETCHED = "fetched"  # → parse.item
    PARSED = "parsed"  # → filter.item
    READY = "ready"  # → ai.classify
    CLASSIFIED = "classified"  # → ai.summarize
    ENRICHED = "enriched"  # terminal: visible (unless is_duplicate)
    FILTERED = "filtered"  # terminal: dropped by a rule
    DUPLICATE = "duplicate"  # terminal: same content/story as another item
    FAILED = "failed"  # terminal: gave up

    TERMINAL = (ENRICHED, FILTERED, DUPLICATE, FAILED)


class ItemCluster(Base):
    """Items from different sources covering the same story."""

    __tablename__ = "item_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_count: Mapped[int] = mapped_column(Integer, server_default="1")
    # The one enriched item shown to readers (best source priority).
    primary_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL", use_alter=True, name="fk_item_clusters_primary_item_id")
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    items: Mapped[list["Item"]] = relationship(back_populates="cluster", foreign_keys="Item.cluster_id")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_items_source_external"),
        Index("ix_items_feed", "status", "is_duplicate", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[str] = mapped_column(String(20), server_default="news")
    # Dedupe key within a source: the canonical URL.
    external_id: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(500))
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    # Feed-provided description (PII-redacted). Fallback content when the
    # article page can't be fetched; the only content for videos.
    feed_summary: Mapped[str | None] = mapped_column(Text)
    # Clean, PII-redacted main text.
    content: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    simhash: Mapped[int | None] = mapped_column(BigInteger)
    language: Mapped[str | None] = mapped_column(String(8))
    raw_path: Mapped[str | None] = mapped_column(String(500))

    status: Mapped[str] = mapped_column(String(20), server_default=ItemStatus.DISCOVERED, index=True)
    status_reason: Mapped[str | None] = mapped_column(String(300))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))

    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("item_clusters.id", ondelete="SET NULL"), index=True)
    # True when another enriched item in the same cluster is shown instead.
    is_duplicate: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    embedding: Mapped[list | None] = mapped_column(Vector(settings.EMBEDDING_DIM))

    # Projections of the latest enrichments, kept on the row for filtering
    # and ranking. The enrichments table remains the source of truth.
    primary_topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), index=True)
    relevance: Mapped[float | None] = mapped_column(Float)  # R, 0-100
    sentiment: Mapped[str | None] = mapped_column(String(20))
    hotness_score: Mapped[float] = mapped_column(Float, server_default="0", index=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=utcnow
    )

    source: Mapped["Source"] = relationship(back_populates="items")
    topic: Mapped["Topic | None"] = relationship()
    cluster: Mapped["ItemCluster | None"] = relationship(back_populates="items", foreign_keys=[cluster_id])


# ---------------------------------------------------------------------- AI


class PipelineVersion(Base):
    """One row per (stage, prompt, schema, provider, model) combination, so
    every enrichment records exactly what produced it."""

    __tablename__ = "pipeline_versions"
    __table_args__ = (
        UniqueConstraint("stage", "name", "provider", "model", "prompt_sha256", name="uq_pipeline_versions"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[str] = mapped_column(String(20))  # classify | summarize
    name: Mapped[str] = mapped_column(String(50))  # e.g. classify-v1
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    json_schema: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Enrichment(Base):
    __tablename__ = "enrichments"
    __table_args__ = (
        UniqueConstraint("item_id", "pipeline_version_id", name="uq_enrichments_item_version"),
        Index("ix_enrichments_item_stage", "item_id", "stage", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    pipeline_version_id: Mapped[int] = mapped_column(ForeignKey("pipeline_versions.id"))
    stage: Mapped[str] = mapped_column(String(20))
    output: Mapped[dict] = mapped_column(JSONB)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


# ---------------------------------------------------------------- job pool


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    DEAD = "dead"
    ACTIVE = (QUEUED, RUNNING)


class Job(Base):
    """Shared work pool. Workers claim rows with FOR UPDATE SKIP LOCKED
    (app/jobs/queue.py); a job's side effects and its completion (plus the
    next step's job) are committed in one transaction."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "queue", "status", "priority", "run_at"),
        Index("ix_jobs_lease", "status", "lease_until"),
        # Only one active (queued/running) job per dedupe key.
        Index(
            "uq_jobs_dedupe_active",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    queue: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(10), server_default=JobStatus.QUEUED)
    priority: Mapped[int] = mapped_column(Integer, server_default="100")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="6")
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------ distribution


class PushSubscription(Base):
    """A browser's Web Push subscription. No user accounts yet (phase 6), so
    the subscription itself is the recipient, with its topic choices."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    # Topic slugs to receive; empty list = every topic.
    topics: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Delivery(Base):
    """Created *before* sending, unique per (recipient, item, channel), so a
    re-run job can never notify twice."""

    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("subscription_id", "item_id", "channel", name="uq_deliveries_recipient_item_channel"),
        Index("ix_deliveries_subscription_sent", "subscription_id", "sent_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("push_subscriptions.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20), server_default="webpush")
    # pending | sent | failed | skipped
    status: Mapped[str] = mapped_column(String(10), server_default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
