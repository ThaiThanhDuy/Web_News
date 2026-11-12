"""Public YouTube counters (views, likes, comments) for recent videos, via
YouTube Data API `videos.list?part=statistics` — 1 quota unit per call of up
to 50 videos. Used as an external engagement signal (services/engagement)."""

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.http import polite_get
from app.models import Item, ItemStatus

logger = logging.getLogger(__name__)

API_URL = "https://www.googleapis.com/youtube/v3/videos"
MAX_AGE_DAYS = 7


def video_id(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.hostname and parts.hostname.endswith("youtu.be"):
        return parts.path.strip("/") or None
    return (parse_qs(parts.query).get("v") or [None])[0]


def refresh(db: Session) -> int:
    if not settings.YOUTUBE_API_KEY:
        return 0
    since = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    items = db.execute(
        select(Item).where(Item.item_type == "video", Item.status == ItemStatus.ENRICHED, Item.published_at >= since)
    ).scalars().all()
    by_id = {vid: item for item in items if (vid := video_id(item.url))}
    ids = list(by_id)
    updated = 0
    now = datetime.now(timezone.utc)
    for start in range(0, len(ids), 50):
        batch = ids[start : start + 50]
        response = polite_get(
            f"{API_URL}?{urlencode({'part': 'statistics', 'id': ','.join(batch)})}",
            extra_headers={"X-Goog-Api-Key": settings.YOUTUBE_API_KEY},
        )
        for entry in json.loads(response.body).get("items", []):
            item = by_id.get(entry.get("id"))
            stats = entry.get("statistics") or {}
            if item is None:
                continue
            item.ext_views = int(stats["viewCount"]) if "viewCount" in stats else None
            item.ext_likes = int(stats["likeCount"]) if "likeCount" in stats else None
            item.ext_comments = int(stats["commentCount"]) if "commentCount" in stats else None
            item.ext_metrics_at = now
            updated += 1
    return updated
