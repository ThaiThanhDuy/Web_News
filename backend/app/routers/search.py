"""Search: words, #hashtags, topics, and semantically related items.

  GET /api/search?q=...          words are AND-ed, accent-insensitive
                                 ("dien thoai" finds "điện thoại");
                                 "#tag" matches an item's AI keywords
  GET /api/search/trending       most frequent hashtags of the last 48h
"""

import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Enrichment, Item, Topic
from app.routers.articles import _to_out, _visible, _with_relations
from app.schemas import CategoryOut, SearchOut, TrendingOut
from app.utils.text import fold, fold_tag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])

MAX_TERMS = 8
_LIKE_ESCAPE = re.compile(r"([\\%_])")


def _like(term: str) -> str:
    return "%" + _LIKE_ESCAPE.sub(r"\\\1", term) + "%"


def _parse(q: str) -> tuple[list[str], list[str], str]:
    """-> (folded plain words, folded hashtags, plain text for embedding)."""
    words, tags, plain = [], [], []
    for token in q.split()[: MAX_TERMS * 2]:
        if token.startswith("#") and len(token) > 1:
            tag = fold_tag(token[1:])
            if tag:
                tags.append(tag)
        else:
            plain.append(token)
            folded = fold(token)
            if folded:
                words.append(folded)
    return words[:MAX_TERMS], tags[:MAX_TERMS], " ".join(plain)


def _keywords_for(db: Session, item_ids: list[int]) -> list[list[str]]:
    if not item_ids:
        return []
    rows = db.execute(
        select(Enrichment.output)
        .where(Enrichment.item_id.in_(item_ids), Enrichment.stage == "summarize")
        .order_by(Enrichment.item_id, Enrichment.created_at.desc())
        .distinct(Enrichment.item_id)
    ).scalars()
    return [[str(k) for k in (out or {}).get("keywords") or []] for out in rows]


def _top_tags(keyword_lists: list[list[str]], limit: int, must_contain: list[str] | None = None) -> list[str]:
    """Most frequent keywords (counted accent-insensitively, displayed in
    their most common original spelling)."""
    counts: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    for keywords in keyword_lists:
        for kw in keywords:
            key = fold_tag(kw)
            if not key or (must_contain and not any(t in key for t in must_contain)):
                continue
            counts[key] += 1
            spellings.setdefault(key, Counter())[kw.strip()] += 1
    return [spellings[key].most_common(1)[0][0] for key, _ in counts.most_common(limit)]


@router.get("", response_model=SearchOut)
def search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    words, tags, plain_text = _parse(q.strip())
    if not words and not tags:
        return SearchOut(query=q, items=[], related=[], topics=[], tags=[])

    # --- lexical: every word and every hashtag must match
    stmt = _visible(select(Item))
    for word in words:
        stmt = stmt.where(Item.search_text.ilike(_like(word), escape="\\"))
    for tag in tags:
        stmt = stmt.where(Item.tags.ilike(_like(tag), escape="\\"))
    # Title comes first in search_text, so matches near the start rank
    # higher; then hotness, then recency.
    position = func.greatest(*[func.strpos(Item.search_text, w) for w in words]) if len(words) > 1 else (
        func.strpos(Item.search_text, words[0]) if words else None
    )
    order = [Item.hotness_score.desc(), Item.published_at.desc()]
    if position is not None:
        order.insert(0, (position > 200).asc())  # "in or near the title" first
    items = list(db.execute(_with_relations(stmt).order_by(*order).limit(limit)).unique().scalars().all())

    # --- topics whose name matches the plain words
    topics = []
    if words:
        joined = " ".join(words)
        for topic in db.execute(select(Topic).where(Topic.is_public.is_(True)).order_by(Topic.sort_order)).scalars():
            name = fold(topic.name)
            if joined in name or all(w in name for w in words) or joined.replace(" ", "-") == topic.slug:
                topics.append(topic)

    # --- related: nearest items by embedding, excluding lexical hits
    related: list[Item] = []
    semantic_text = plain_text or " ".join(f"{t}" for t in q.replace("#", " ").split())
    if settings.EMBEDDINGS_ENABLED and semantic_text.strip():
        try:
            from app.services.embeddings import embed_text

            vector = embed_text(semantic_text)
            distance = Item.embedding.cosine_distance(vector)
            exclude = [i.id for i in items] or [-1]
            related = list(
                db.execute(
                    _with_relations(_visible(select(Item)))
                    .where(
                        Item.embedding.is_not(None),
                        Item.id.notin_(exclude),
                        distance < settings.SEARCH_RELATED_MAX_DISTANCE,
                    )
                    .order_by(distance)
                    .limit(8)
                )
                .unique()
                .scalars()
                .all()
            )
        except Exception:  # never fail the search because of embeddings
            logger.exception("semantic search failed")

    tag_terms = tags + [w.replace(" ", "") for w in words]
    suggestions = _top_tags(_keywords_for(db, [i.id for i in items + related]), 8, must_contain=tag_terms)

    return SearchOut(
        query=q,
        items=_to_out(items, db),
        related=_to_out(related, db),
        topics=[CategoryOut.model_validate(t) for t in topics[:4]],
        tags=suggestions,
    )


@router.get("/trending", response_model=TrendingOut)
def trending(limit: int = Query(12, ge=1, le=30), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=48)
    ids = list(db.execute(_visible(select(Item.id)).where(Item.published_at >= since)).scalars())
    return TrendingOut(tags=_top_tags(_keywords_for(db, ids), limit))
