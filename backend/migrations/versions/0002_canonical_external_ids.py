"""Canonicalize external_id of rows migrated from the legacy `articles`
table: those kept the raw feed URL (e.g. with a trailing slash), while
connectors key items by app.utils.text.canonical_url — so every re-fetch of
an old article inserted a second row that only the content-hash check then
caught. Rows whose canonical id already exists in the same source are left
as they are (that duplicate is already resolved).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

from app.utils.text import canonical_url

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, source_id, external_id FROM items")).all()
    taken = {(r.source_id, r.external_id) for r in rows}
    for r in rows:
        canonical = canonical_url(r.external_id)[:1000]
        if canonical == r.external_id or (r.source_id, canonical) in taken:
            continue
        bind.execute(sa.text("UPDATE items SET external_id = :e WHERE id = :id"), {"e": canonical, "id": r.id})
        taken.discard((r.source_id, r.external_id))
        taken.add((r.source_id, canonical))


def downgrade() -> None:
    pass  # not reversible (original ids not kept); harmless to leave canonical
