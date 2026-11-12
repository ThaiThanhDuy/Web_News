"""Fill items.language for rows migrated from the legacy schema (they
skipped the parse step that sets it), so the language filter sees them.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op

from app.utils.text import detect_language

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, title, coalesce(content, feed_summary, '') AS body FROM items WHERE language IS NULL")
    ).all()
    for r in rows:
        bind.execute(
            sa.text("UPDATE items SET language = :lang WHERE id = :id"),
            {"lang": detect_language(f"{r.title}\n{r.body}"), "id": r.id},
        )


def downgrade() -> None:
    pass
