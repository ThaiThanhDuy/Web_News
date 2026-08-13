"""Fetches and normalizes RSS feed items for a single source.

All three sources (VnExpress, GenK, VietnamNet) reject requests without a
browser-like User-Agent (GenK in particular returns 503 without one), so we
fetch the raw bytes with `requests` first and hand them to `feedparser`
instead of letting feedparser do its own HTTP request.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

from app.constants import DEFAULT_USER_AGENT

IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)
# Matches a non-standard 2-digit UTC offset (e.g. GenK emits "+07" instead of
# the RFC 822 "+0700"), which neither feedparser nor email.utils can parse.
SHORT_TZ_OFFSET_RE = re.compile(r"([+-]\d{2})$")


@dataclass
class FeedItem:
    title: str
    url: str
    published_at: datetime
    thumbnail_url: str | None
    # Feed-provided summary/description (e.g. a YouTube video's description,
    # exposed by feedparser as `summary`). Used as article content for
    # sources where there's no article page to scrape — see
    # constants.VIDEO_SOURCE_SLUGS.
    description: str | None = None


def _extract_thumbnail(entry: dict) -> str | None:
    # 1) <enclosure type="image/..."> (VnExpress)
    for enclosure in entry.get("enclosures", []) or []:
        href = enclosure.get("href") or enclosure.get("url")
        if href and enclosure.get("type", "").startswith("image"):
            return href

    # 2) media:thumbnail / media:content — thumbnail first, since
    # media:content can point at non-image media (e.g. YouTube's RSS puts a
    # Flash embed placeholder there, not a picture).
    media_thumb = entry.get("media_thumbnail") or []
    if media_thumb and media_thumb[0].get("url"):
        return media_thumb[0]["url"]
    media_content = entry.get("media_content") or []
    if media_content and media_content[0].get("url") and media_content[0].get("type", "").startswith("image"):
        return media_content[0]["url"]

    # 3) first <img src="..."> inside the HTML description (GenK, VietnamNet)
    summary = entry.get("summary", "") or entry.get("description", "")
    match = IMG_SRC_RE.search(summary)
    if match:
        return match.group(1)

    # 4) first <img src="..."> inside <content:encoded> (Mashable puts the
    # thumbnail here instead of in the description or any media tag)
    for content_block in entry.get("content", []) or []:
        match = IMG_SRC_RE.search(content_block.get("value", ""))
        if match:
            return match.group(1)

    return None


def _parse_published(entry: dict) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc)

    raw = entry.get("published") or entry.get("updated")
    if raw:
        normalized = SHORT_TZ_OFFSET_RE.sub(lambda m: f"{m.group(1)}00", raw.strip())
        try:
            dt = parsedate_to_datetime(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass

    return datetime.now(timezone.utc)


def fetch_feed_items(rss_url: str, timeout: int = 15) -> list[FeedItem]:
    response = requests.get(rss_url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
    response.raise_for_status()

    parsed = feedparser.parse(response.content)
    items: list[FeedItem] = []
    for entry in parsed.entries:
        url = entry.get("link")
        title = (entry.get("title") or "").strip()
        if not url or not title:
            continue
        items.append(
            FeedItem(
                title=title,
                url=url,
                published_at=_parse_published(entry),
                thumbnail_url=_extract_thumbnail(entry),
                description=(entry.get("summary") or "").strip() or None,
            )
        )
    return items
