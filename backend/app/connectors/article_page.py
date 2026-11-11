"""Second crawl step for news items: download the article page and extract
its main text (trafilatura drops menus, ads and comments) plus og:image."""

import re
from dataclasses import dataclass

import trafilatura

from app.connectors.http import polite_get
from app.utils.text import clean_text

OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE
)
OG_IMAGE_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']', re.IGNORECASE
)


@dataclass
class ArticlePage:
    final_url: str
    http_status: int
    text: str | None  # cleaned + PII-redacted main text, None if too short
    og_image: str | None


def fetch_article_page(url: str) -> ArticlePage:
    response = polite_get(url)
    page = response.text
    extracted = trafilatura.extract(
        page, url=url, include_comments=False, include_tables=False, favor_recall=True
    )
    text = clean_text(extracted)
    match = OG_IMAGE_RE.search(page) or OG_IMAGE_RE_ALT.search(page)
    return ArticlePage(
        final_url=response.url,
        http_status=response.status,
        text=text if len(text) >= 100 else None,
        og_image=match.group(1) if match else None,
    )
