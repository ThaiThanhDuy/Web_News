"""RSS/Atom connector — news sites and YouTube channel feeds alike.

Several sources (GenK in particular) reject requests without a browser-like
User-Agent, so the bytes are fetched with polite_get and handed to
feedparser rather than letting feedparser do its own HTTP request.
"""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from app.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from app.connectors.http import polite_get
from app.models import Source
from app.utils.text import canonical_url, clean_text

IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)
# GenK emits a non-standard 2-digit UTC offset ("+07" instead of "+0700"),
# which neither feedparser nor email.utils can parse.
SHORT_TZ_OFFSET_RE = re.compile(r"([+-]\d{2})$")


def _extract_thumbnail(entry: dict) -> str | None:
    # 1) <enclosure type="image/..."> (VnExpress)
    for enclosure in entry.get("enclosures", []) or []:
        href = enclosure.get("href") or enclosure.get("url")
        if href and enclosure.get("type", "").startswith("image"):
            return href
    # 2) media:thumbnail, then media:content when it's an image (YouTube puts
    # a Flash embed placeholder in media:content, not a picture).
    media_thumb = entry.get("media_thumbnail") or []
    if media_thumb and media_thumb[0].get("url"):
        return media_thumb[0]["url"]
    media_content = entry.get("media_content") or []
    if media_content and media_content[0].get("url") and media_content[0].get("type", "").startswith("image"):
        return media_content[0]["url"]
    # 3) first <img> in the description (GenK, VietnamNet) or content:encoded
    summary = entry.get("summary", "") or entry.get("description", "")
    match = IMG_SRC_RE.search(summary)
    if match:
        return match.group(1)
    for block in entry.get("content", []) or []:
        match = IMG_SRC_RE.search(block.get("value", ""))
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
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


class RssConnector(BaseConnector):
    def fetch(self, source: Source, cursor: dict) -> FetchResult:
        response = polite_get(source.feed_url, etag=cursor.get("etag"), last_modified=cursor.get("last_modified"))
        if response.not_modified:
            return FetchResult(items=[], cursor=cursor, http_status=304, not_modified=True)

        parsed = feedparser.parse(response.body)
        items: list[DiscoveredItem] = []
        for entry in parsed.entries:
            url = entry.get("link")
            title = clean_text(entry.get("title") or "")
            if not url or not title:
                continue
            items.append(
                DiscoveredItem(
                    external_id=canonical_url(url),
                    url=url,
                    title=title[:500],
                    published_at=_parse_published(entry),
                    thumbnail_url=_extract_thumbnail(entry),
                    summary=clean_text(entry.get("summary") or "") or None,
                )
            )

        new_cursor = dict(cursor)
        new_cursor["etag"] = response.headers.get("etag")
        new_cursor["last_modified"] = response.headers.get("last-modified")
        warnings = [f"feed parse issue: {parsed.bozo_exception}"] if parsed.bozo and not items else []
        return FetchResult(items=items, cursor=new_cursor, http_status=response.status, warnings=warnings)
