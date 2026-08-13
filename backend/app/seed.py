"""Idempotent seed of the fixed sources & categories rows. Safe to run repeatedly.

Existing rows are kept in sync with app/constants.py (not just inserted once),
so editing e.g. a source's logo_url there and restarting the API is enough —
no separate migration needed for these two tables.
"""

from sqlalchemy.orm import Session

from app.constants import CATEGORIES, SOURCES
from app.models import Category, Source

_SOURCE_FIELDS = ("name", "homepage_url", "logo_url", "rss_url")
_CATEGORY_FIELDS = ("name",)


def seed_sources_and_categories(db: Session) -> None:
    existing_sources = {s.slug: s for s in db.query(Source).all()}
    for src in SOURCES:
        existing = existing_sources.get(src["slug"])
        if existing is None:
            db.add(Source(**src))
            continue
        for field in _SOURCE_FIELDS:
            setattr(existing, field, src[field])

    existing_categories = {c.slug: c for c in db.query(Category).all()}
    for cat in CATEGORIES:
        existing = existing_categories.get(cat["slug"])
        if existing is None:
            db.add(Category(**cat))
            continue
        for field in _CATEGORY_FIELDS:
            setattr(existing, field, cat[field])

    db.commit()
