"""Hot-news analytics: keyword trends (daily stats + current trend),
anonymous reader engagement (hourly per item, per feed position), search
query stats, YouTube public counters and cached ranking inputs on items.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, type_ in (
        ("trend_score", sa.Float()),
        ("engagement_score", sa.Float()),
        ("ext_views", sa.BigInteger()),
        ("ext_likes", sa.BigInteger()),
        ("ext_comments", sa.BigInteger()),
        ("ext_metrics_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("items", sa.Column(name, type_))

    op.create_table(
        "keyword_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("keyword", sa.String(200), primary_key=True),
        sa.Column("display", sa.String(200), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "keyword_trends",
        sa.Column("keyword", sa.String(200), primary_key=True),
        sa.Column("display", sa.String(200), nullable=False),
        sa.Column("recent_24h", sa.Integer(), nullable=False),
        sa.Column("sources_24h", sa.Integer(), nullable=False),
        sa.Column("baseline_daily", sa.Float(), nullable=False),
        sa.Column("lift", sa.Float(), nullable=False),
        sa.Column("heat", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_keyword_trends_heat", "keyword_trends", ["heat"])
    op.create_table(
        "item_engagement_hourly",
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("hour", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tag_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("push_opens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_clicks", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_item_engagement_hourly_hour", "item_engagement_hourly", ["hour"])
    op.create_table(
        "feed_position_stats",
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "search_queries_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("query", sa.String(200), primary_key=True),
        sa.Column("display", sa.String(200), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    for table in ("search_queries_daily", "feed_position_stats", "item_engagement_hourly", "keyword_trends", "keyword_daily"):
        op.drop_table(table)
    for name in ("ext_metrics_at", "ext_comments", "ext_likes", "ext_views", "engagement_score", "trend_score"):
        op.drop_column("items", name)
