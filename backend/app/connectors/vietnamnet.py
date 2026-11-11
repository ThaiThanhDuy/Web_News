"""VietnamNet connector.

VietnamNet's own RSS feed (cong-nghe.rss) has been stuck returning the same
year-old items, but the category page embeds an up-to-date schema.org
`ItemList` of the latest articles as JSON-LD — structured data on the page,
which is what this reads.
"""

import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from app.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from app.connectors.http import polite_get
from app.models import Source
from app.utils.text import canonical_url, clean_text

JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def _parse_date(raw: str | None) -> datetime:
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace(" ", ""))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class VietnamnetJsonLdConnector(BaseConnector):
    def fetch(self, source: Source, cursor: dict) -> FetchResult:
        response = polite_get(source.feed_url, etag=cursor.get("etag"), last_modified=cursor.get("last_modified"))
        if response.not_modified:
            return FetchResult(items=[], cursor=cursor, http_status=304, not_modified=True)

        items: list[DiscoveredItem] = []
        for raw_block in JSON_LD_RE.findall(response.text):
            try:
                data = json.loads(raw_block)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("@type") != "ItemList":
                continue
            for entry in data.get("itemListElement", []):
                article = entry.get("item") or {}
                if article.get("@type") != "NewsArticle":
                    continue
                url, headline = article.get("url"), article.get("headline")
                if not url or not headline:
                    continue
                absolute = urljoin(source.feed_url, url)
                items.append(
                    DiscoveredItem(
                        external_id=canonical_url(absolute),
                        url=absolute,
                        title=clean_text(str(headline))[:500],
                        published_at=_parse_date(article.get("datePublished")),
                        thumbnail_url=(article.get("image") or {}).get("url"),
                        summary=clean_text(article.get("description") or "") or None,
                    )
                )

        new_cursor = dict(cursor)
        new_cursor["etag"] = response.headers.get("etag")
        new_cursor["last_modified"] = response.headers.get("last-modified")
        return FetchResult(items=items, cursor=new_cursor, http_status=response.status)
