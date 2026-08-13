"""VietnamNet-specific scraper.

VietnamNet's own RSS feed (cong-nghe.rss) has been stuck returning the same
handful of year-old items — it isn't being refreshed. The category page
itself, however, embeds an up-to-date schema.org `ItemList` of the latest
articles as JSON-LD, which is what we read here instead.
"""

import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests

from app.constants import DEFAULT_USER_AGENT
from app.scraper.rss_fetcher import FeedItem

JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def fetch_vietnamnet_items(page_url: str, timeout: int = 15) -> list[FeedItem]:
    response = requests.get(page_url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
    response.raise_for_status()

    items: list[FeedItem] = []
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

            url = article.get("url")
            headline = article.get("headline")
            if not url or not headline:
                continue

            thumbnail = (article.get("image") or {}).get("url")

            items.append(
                FeedItem(
                    title=str(headline).strip(),
                    url=urljoin(page_url, url),
                    published_at=_parse_date(article.get("datePublished")),
                    thumbnail_url=thumbnail,
                )
            )

    return items


def _parse_date(raw: str | None) -> datetime:
    if raw:
        try:
            return datetime.fromisoformat(raw.replace(" ", ""))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
