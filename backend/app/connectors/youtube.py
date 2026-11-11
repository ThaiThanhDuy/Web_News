"""YouTube channel connector via the official YouTube Data API v3.

YouTube's robots.txt disallows /feeds/videos.xml for every crawler, so the
channel RSS feed is off limits; the Data API is the sanctioned route.

Cost: one `playlistItems.list` call (1 quota unit) per fetch on the
channel's "uploads" playlist (UU + channel id without its UC prefix) —
`search.list` (100 units) is never used. Default quota is 10,000 units/day.
Only title, description, publish time and thumbnail are kept; no comments,
audio or captions.

sources.feed_url = https://www.youtube.com/channel/<channel id>
Needs YOUTUBE_API_KEY (Google Cloud console → YouTube Data API v3).
"""

import json
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

from app.config import settings
from app.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from app.connectors.http import polite_get
from app.models import Source
from app.utils.text import canonical_url, clean_text

API_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


class ConnectorNotConfigured(ValueError):
    pass


def channel_id_from(feed_url: str) -> str:
    path = urlsplit(feed_url).path.rstrip("/")
    if "/channel/" not in path:
        raise ConnectorNotConfigured(f"feed_url must be https://www.youtube.com/channel/<id>, got {feed_url}")
    channel_id = path.rsplit("/", 1)[-1]
    if not channel_id.startswith("UC"):
        raise ConnectorNotConfigured(f"not a channel id: {channel_id}")
    return channel_id


def _best_thumbnail(thumbnails: dict) -> str | None:
    for size in ("maxres", "standard", "high", "medium", "default"):
        url = (thumbnails.get(size) or {}).get("url")
        if url:
            return url
    return None


class YouTubeApiConnector(BaseConnector):
    def fetch(self, source: Source, cursor: dict) -> FetchResult:
        if not settings.YOUTUBE_API_KEY:
            raise ConnectorNotConfigured("YOUTUBE_API_KEY is not set in backend/.env")
        uploads = "UU" + channel_id_from(source.feed_url)[2:]
        query = urlencode({"part": "snippet,contentDetails", "playlistId": uploads, "maxResults": 25})
        # Key goes in a header, never the URL, so it can't leak into logs/DB.
        response = polite_get(
            f"{API_URL}?{query}",
            etag=cursor.get("etag"),
            extra_headers={"X-Goog-Api-Key": settings.YOUTUBE_API_KEY},
        )
        if response.not_modified:
            return FetchResult(items=[], cursor=cursor, http_status=304, not_modified=True)

        data = json.loads(response.body)
        items: list[DiscoveredItem] = []
        for entry in data.get("items", []):
            snippet = entry.get("snippet") or {}
            video_id = (entry.get("contentDetails") or {}).get("videoId") or (snippet.get("resourceId") or {}).get(
                "videoId"
            )
            title = clean_text(snippet.get("title") or "")
            if not video_id or not title or title in ("Private video", "Deleted video"):
                continue
            published = (entry.get("contentDetails") or {}).get("videoPublishedAt") or snippet.get("publishedAt")
            try:
                published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                published_at = datetime.now(timezone.utc)
            url = f"https://www.youtube.com/watch?v={video_id}"
            items.append(
                DiscoveredItem(
                    external_id=canonical_url(url),
                    url=url,
                    title=title[:500],
                    published_at=published_at,
                    thumbnail_url=_best_thumbnail(snippet.get("thumbnails") or {}),
                    summary=clean_text(snippet.get("description") or "") or None,
                )
            )
        new_cursor = dict(cursor)
        new_cursor["etag"] = data.get("etag") or response.headers.get("etag")
        return FetchResult(items=items, cursor=new_cursor, http_status=response.status)
