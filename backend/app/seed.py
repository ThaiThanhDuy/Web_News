"""Idempotent sync of the fixed sources & topics rows from app/constants.py.
Safe to run repeatedly (the API runs it on startup).

Only the static configuration columns are overwritten — runtime crawl
state (next_run_at, cursor, failure counters, pause) is left untouched.
"""

from sqlalchemy.orm import Session

from app.constants import SOURCES, TOPICS
from app.models import Source, Topic

_SOURCE_FIELDS = (
    "name",
    "homepage_url",
    "logo_url",
    "feed_url",
    "connector",
    "item_type",
    "priority",
    "trust",
    "fetch_interval_minutes",
)


def seed_sources_and_topics(db: Session) -> None:
    existing_sources = {s.slug: s for s in db.query(Source).all()}
    for src in SOURCES:
        existing = existing_sources.get(src["slug"])
        if existing is None:
            db.add(Source(**src))
            continue
        for field in _SOURCE_FIELDS:
            setattr(existing, field, src[field])

    existing_topics = {t.slug: t for t in db.query(Topic).all()}
    for order, topic in enumerate(TOPICS):
        existing = existing_topics.get(topic["slug"])
        if existing is None:
            db.add(Topic(slug=topic["slug"], name=topic["name"], is_public=True, sort_order=order))
            continue
        existing.name = topic["name"]
        existing.sort_order = order

    db.commit()
