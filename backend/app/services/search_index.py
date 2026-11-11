"""Builds the accent-folded search columns of an item from its summary."""

from app.models import Item
from app.utils.text import fold, fold_tag


def index_item(item: Item, summary: dict | None, topic_name: str | None) -> None:
    summary = summary or {}
    keywords = [str(k) for k in summary.get("keywords") or []]
    parts = [
        item.title,
        summary.get("one_line_takeaway") or "",
        " ".join(str(b) for b in summary.get("summary_bullets") or []),
        " ".join(keywords),
        topic_name or "",
        item.source.name if item.source else "",
    ]
    # Title comes first: ranking prefers matches near the start.
    item.search_text = fold(" \n ".join(p for p in parts if p))
    tags = [t for t in (fold_tag(k) for k in keywords) if t]
    item.tags = f"|{'|'.join(tags)}|" if tags else None
