"""Core schema: sources/topics/items/clusters, AI pipeline versions and
enrichments, the Postgres job pool, and Web Push distribution.

If the pre-Alembic tables (sources, categories, articles, article_clusters)
exist, their data is carried over — ids are preserved — and the legacy
tables are dropped:
  - articles        -> items (+ enrichments for already-processed rows,
                       recorded under a "legacy-v0" pipeline version)
  - article_clusters-> item_clusters
  - categories      -> topics
  - sources         -> sources (new crawl-state columns use defaults;
                       app.seed fills in connector/priority/trust)
Unprocessed legacy articles restart the new pipeline from "discovered".

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384
NOW = sa.text("now()")


def _ts(name: str, nullable: bool = True, default=None) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def upgrade() -> None:
    bind = op.get_bind()
    legacy = sa.inspect(bind).has_table("articles")

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if legacy:
        # Snapshot legacy rows into session-local temp tables, then drop the
        # originals so the new tables can reuse their names (index and
        # constraint names are schema-global in Postgres).
        for table in ("sources", "categories", "article_clusters", "articles"):
            op.execute(f"CREATE TEMP TABLE legacy_{table} ON COMMIT DROP AS SELECT * FROM {table}")
        op.execute("DROP TABLE articles, article_clusters, categories, sources CASCADE")

    # ------------------------------------------------------------ sources
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("homepage_url", sa.String(255), nullable=False),
        sa.Column("logo_url", sa.String(500), nullable=False),
        sa.Column("feed_url", sa.String(500), nullable=False),
        sa.Column("connector", sa.String(30), nullable=False, server_default="rss"),
        sa.Column("item_type", sa.String(20), nullable=False, server_default="news"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("trust", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("fetch_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        _ts("next_run_at", nullable=False, default=NOW),
        sa.Column("cursor", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        _ts("paused_until"),
        _ts("last_fetch_at"),
        _ts("last_success_at"),
        sa.Column("last_error", sa.Text()),
        sa.UniqueConstraint("feed_url"),
    )
    op.create_index("ix_sources_slug", "sources", ["slug"], unique=True)

    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        _ts("started_at", nullable=False, default=NOW),
        _ts("finished_at"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_fetch_runs_source_id", "fetch_runs", ["source_id"])
    op.create_index("ix_fetch_runs_started_at", "fetch_runs", ["started_at"])

    # ------------------------------------------------------------- topics
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
    )
    op.create_index("ix_topics_slug", "topics", ["slug"], unique=True)

    # ------------------------------------------------------------ content
    op.create_table(
        "item_clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("primary_item_id", sa.Integer()),
        _ts("first_seen_at", nullable=False, default=NOW),
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(20), nullable=False, server_default="news"),
        sa.Column("external_id", sa.String(1000), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("thumbnail_url", sa.String(1000)),
        _ts("published_at", nullable=False),
        _ts("discovered_at", nullable=False, default=NOW),
        sa.Column("feed_summary", sa.Text()),
        sa.Column("content", sa.Text()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("simhash", sa.BigInteger()),
        sa.Column("language", sa.String(8)),
        sa.Column("raw_path", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="discovered"),
        sa.Column("status_reason", sa.String(300)),
        sa.Column("duplicate_of_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="SET NULL")),
        sa.Column("cluster_id", sa.Integer(), sa.ForeignKey("item_clusters.id", ondelete="SET NULL")),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("primary_topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="SET NULL")),
        sa.Column("relevance", sa.Float()),
        sa.Column("sentiment", sa.String(20)),
        sa.Column("hotness_score", sa.Float(), nullable=False, server_default="0"),
        _ts("enriched_at"),
        _ts("updated_at", nullable=False, default=NOW),
        sa.UniqueConstraint("source_id", "external_id", name="uq_items_source_external"),
    )
    op.create_index("ix_items_source_id", "items", ["source_id"])
    op.create_index("ix_items_published_at", "items", ["published_at"])
    op.create_index("ix_items_content_hash", "items", ["content_hash"])
    op.create_index("ix_items_status", "items", ["status"])
    op.create_index("ix_items_cluster_id", "items", ["cluster_id"])
    op.create_index("ix_items_primary_topic_id", "items", ["primary_topic_id"])
    op.create_index("ix_items_hotness_score", "items", ["hotness_score"])
    op.create_index("ix_items_feed", "items", ["status", "is_duplicate", "published_at"])
    op.create_foreign_key(
        "fk_item_clusters_primary_item_id", "item_clusters", "items", ["primary_item_id"], ["id"], ondelete="SET NULL"
    )

    # ----------------------------------------------------------------- AI
    op.create_table(
        "pipeline_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("json_schema", JSONB(), nullable=False),
        _ts("created_at", nullable=False, default=NOW),
        sa.UniqueConstraint("stage", "name", "provider", "model", "prompt_sha256", name="uq_pipeline_versions"),
    )

    op.create_table(
        "enrichments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pipeline_version_id", sa.Integer(), sa.ForeignKey("pipeline_versions.id"), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("output", JSONB(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        _ts("created_at", nullable=False, default=NOW),
        sa.UniqueConstraint("item_id", "pipeline_version_id", name="uq_enrichments_item_version"),
    )
    op.create_index("ix_enrichments_item_stage", "enrichments", ["item_id", "stage", "created_at"])

    # ----------------------------------------------------------- job pool
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("queue", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(10), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        _ts("run_at", nullable=False, default=NOW),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("dedupe_key", sa.String(200)),
        sa.Column("locked_by", sa.String(100)),
        _ts("lease_until"),
        sa.Column("last_error", sa.Text()),
        _ts("created_at", nullable=False, default=NOW),
        _ts("updated_at", nullable=False, default=NOW),
        _ts("finished_at"),
    )
    op.create_index("ix_jobs_claim", "jobs", ["queue", "status", "priority", "run_at"])
    op.create_index("ix_jobs_lease", "jobs", ["status", "lease_until"])
    op.create_index(
        "uq_jobs_dedupe_active",
        "jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    # ------------------------------------------------------- distribution
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("topics", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("user_agent", sa.String(300)),
        _ts("created_at", nullable=False, default=NOW),
        _ts("updated_at", nullable=False, default=NOW),
        _ts("last_sent_at"),
        sa.UniqueConstraint("endpoint"),
    )

    op.create_table(
        "deliveries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("push_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="webpush"),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text()),
        _ts("created_at", nullable=False, default=NOW),
        _ts("sent_at"),
        sa.UniqueConstraint("subscription_id", "item_id", "channel", name="uq_deliveries_recipient_item_channel"),
    )
    op.create_index("ix_deliveries_item_id", "deliveries", ["item_id"])
    op.create_index("ix_deliveries_subscription_sent", "deliveries", ["subscription_id", "sent_at"])

    if legacy:
        _migrate_legacy_data()


def _migrate_legacy_data() -> None:
    op.execute(
        """
        INSERT INTO sources (id, slug, name, homepage_url, logo_url, feed_url, item_type)
        SELECT id, slug, name, homepage_url, logo_url, rss_url,
               CASE WHEN slug LIKE 'yt-%' THEN 'video' ELSE 'news' END
        FROM legacy_sources
        """
    )
    op.execute(
        """
        INSERT INTO topics (id, slug, name)
        SELECT id, slug, name FROM legacy_categories
        """
    )
    op.execute(
        """
        INSERT INTO item_clusters (id, source_count, first_seen_at)
        SELECT id, source_count, created_at FROM legacy_article_clusters
        """
    )
    op.execute(
        """
        INSERT INTO items (
            id, source_id, item_type, external_id, url, title, thumbnail_url,
            published_at, discovered_at, feed_summary, content, status, status_reason,
            cluster_id, is_duplicate, embedding, primary_topic_id, relevance, sentiment,
            hotness_score, enriched_at
        )
        SELECT a.id, a.source_id,
               CASE WHEN s.slug LIKE 'yt-%' THEN 'video' ELSE 'news' END,
               a.original_url, a.original_url, a.title, a.thumbnail_url,
               a.published_at, a.scraped_at,
               CASE WHEN s.slug LIKE 'yt-%' THEN a.raw_content END,
               CASE WHEN a.is_processed THEN a.raw_content END,
               CASE WHEN a.is_processed THEN 'enriched' ELSE 'discovered' END,
               'migrated from articles',
               CASE WHEN a.is_processed THEN a.cluster_id END,
               CASE WHEN a.is_processed THEN a.is_duplicate ELSE false END,
               CASE WHEN a.is_processed THEN a.embedding END,
               a.category_id, a.ai_hotness_score, a.sentiment,
               COALESCE(a.hotness_score, 0),
               CASE WHEN a.is_processed THEN a.scraped_at END
        FROM legacy_articles a
        JOIN legacy_sources s ON s.id = a.source_id
        """
    )
    op.execute(
        """
        UPDATE item_clusters c SET primary_item_id = l.primary_article_id
        FROM legacy_article_clusters l
        WHERE l.id = c.id AND l.primary_article_id IN (SELECT id FROM items WHERE status = 'enriched')
        """
    )

    # Already-processed legacy rows keep their AI output as enrichments of a
    # "legacy-v0" pipeline version (model/prompt unknown).
    op.execute(
        """
        INSERT INTO pipeline_versions (stage, name, provider, model, prompt_sha256, json_schema)
        VALUES ('classify',  'legacy-v0', 'legacy', 'unknown', repeat('0', 64), '{}'::jsonb),
               ('summarize', 'legacy-v0', 'legacy', 'unknown', repeat('0', 64), '{}'::jsonb)
        """
    )
    op.execute(
        """
        INSERT INTO enrichments (item_id, pipeline_version_id, stage, output, created_at)
        SELECT a.id, pv.id, 'classify',
               jsonb_build_object('topic', c.slug, 'relevance', a.ai_hotness_score, 'sentiment', a.sentiment),
               a.scraped_at
        FROM legacy_articles a
        LEFT JOIN legacy_categories c ON c.id = a.category_id
        JOIN pipeline_versions pv ON pv.stage = 'classify' AND pv.name = 'legacy-v0'
        WHERE a.is_processed
        """
    )
    op.execute(
        """
        INSERT INTO enrichments (item_id, pipeline_version_id, stage, output, created_at)
        SELECT a.id, pv.id, 'summarize',
               jsonb_build_object(
                   'summary_bullets', a.summary_bullets,
                   'one_line_takeaway', a.one_line_takeaway,
                   'keywords', a.keywords
               ),
               a.scraped_at
        FROM legacy_articles a
        JOIN pipeline_versions pv ON pv.stage = 'summarize' AND pv.name = 'legacy-v0'
        WHERE a.is_processed
        """
    )

    for table in ("sources", "topics", "item_clusters", "items"):
        op.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) "
            f"FROM {table}"
        )


def downgrade() -> None:
    # The legacy schema is not restored — this only removes the new tables.
    op.drop_constraint("fk_item_clusters_primary_item_id", "item_clusters", type_="foreignkey")
    for table in (
        "deliveries",
        "push_subscriptions",
        "jobs",
        "enrichments",
        "pipeline_versions",
        "items",
        "item_clusters",
        "topics",
        "fetch_runs",
        "sources",
    ):
        op.drop_table(table)
