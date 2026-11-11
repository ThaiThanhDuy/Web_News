"""Search: accent-folded items.search_text and items.tags, backfilled from
each enriched item's latest summary.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

from app.utils.text import fold, fold_tag

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("search_text", sa.Text()))
    op.add_column("items", sa.Column("tags", sa.Text()))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT i.id, i.title, s.name AS source_name, t.name AS topic_name, e.output
            FROM items i
            JOIN sources s ON s.id = i.source_id
            LEFT JOIN topics t ON t.id = i.primary_topic_id
            LEFT JOIN LATERAL (
                SELECT output FROM enrichments
                WHERE item_id = i.id AND stage = 'summarize'
                ORDER BY created_at DESC LIMIT 1
            ) e ON true
            WHERE i.status = 'enriched'
            """
        )
    ).all()
    for r in rows:
        out = r.output or {}
        keywords = [str(k) for k in out.get("keywords") or []]
        parts = [
            r.title,
            out.get("one_line_takeaway") or "",
            " ".join(str(b) for b in out.get("summary_bullets") or []),
            " ".join(keywords),
            r.topic_name or "",
            r.source_name or "",
        ]
        tags = [t for t in (fold_tag(k) for k in keywords) if t]
        bind.execute(
            sa.text("UPDATE items SET search_text = :s, tags = :t WHERE id = :id"),
            {"s": fold(" \n ".join(p for p in parts if p)), "t": f"|{'|'.join(tags)}|" if tags else None, "id": r.id},
        )


def downgrade() -> None:
    op.drop_column("items", "tags")
    op.drop_column("items", "search_text")
