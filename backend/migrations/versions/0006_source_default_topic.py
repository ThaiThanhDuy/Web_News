"""sources.default_topic: sources dedicated to one topic (e.g. economy desks)
skip the AI classify call — their items get this topic directly.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("default_topic", sa.String(50)))


def downgrade() -> None:
    op.drop_column("sources", "default_topic")
