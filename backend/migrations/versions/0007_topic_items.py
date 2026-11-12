"""topic_items: an item can belong to several topics — its primary topic
(items.primary_topic_id, is_primary) plus related ones from the summarize
stage. Category pages list every item linked to the topic. Backfilled with
each enriched item's primary topic.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_items",
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_topic_items_topic_id", "topic_items", ["topic_id"])
    op.execute(
        """
        INSERT INTO topic_items (item_id, topic_id, is_primary)
        SELECT id, primary_topic_id, true FROM items
        WHERE primary_topic_id IS NOT NULL AND status = 'enriched'
        """
    )


def downgrade() -> None:
    op.drop_table("topic_items")
