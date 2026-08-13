"""Fetches an article page once and extracts (clean text, og:image URL) from it."""

import re

import requests
import trafilatura

from app.constants import DEFAULT_USER_AGENT

OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE
)
OG_IMAGE_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']', re.IGNORECASE
)


def fetch_article(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    """Returns (clean_text, og_image_url). Either may be None on failure."""
    try:
        response = requests.get(url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return None, None

    text = trafilatura.extract(
        response.text,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
    )
    clean_text = text.strip() if text and len(text.strip()) >= 100 else None

    match = OG_IMAGE_RE.search(response.text) or OG_IMAGE_RE_ALT.search(response.text)
    og_image = match.group(1) if match else None

    return clean_text, og_image
