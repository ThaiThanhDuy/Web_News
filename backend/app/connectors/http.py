"""Polite HTTP for every connector and article-page fetch:

  - robots.txt is checked before each request (cached in Redis)
  - requests to one domain are spaced CRAWL_DOMAIN_INTERVAL_SECONDS apart,
    across all worker processes (Redis), i.e. ~1 request at a time per domain
  - conditional GET (ETag / Last-Modified)
  - response size capped at CRAWL_MAX_BYTES
  - login walls, CAPTCHAs and rate limits raise BlockedError: we stop, we
    never try to get around them
"""

import logging
import time
from dataclasses import dataclass, field
from urllib import robotparser
from urllib.parse import urlsplit

import requests

from app.config import settings
from app.jobs.errors import Reschedule
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

_BLOCK_STATUSES = {401, 403, 407, 429, 451}
_CAPTCHA_MARKERS = ("captcha", "cf-challenge", "challenge-platform", "are you a robot", "verify you are human")

# Atomic "reserve the next slot for this domain": returns how many ms the
# caller must wait before its request (0 = go now).
_THROTTLE_LUA = """
local now = tonumber(ARGV[1])
local interval = tonumber(ARGV[2])
local next_at = tonumber(redis.call('GET', KEYS[1]) or '0')
local slot = math.max(now, next_at)
redis.call('SET', KEYS[1], slot + interval, 'PX', interval * 2 + 60000)
return slot - now
"""


class BlockedError(Exception):
    """The site asked us to stop (auth wall, CAPTCHA, 403/429, robots)."""

    def __init__(self, message: str, http_status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.http_status = http_status
        self.retry_after = retry_after


@dataclass
class HttpResult:
    url: str
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    not_modified: bool = False

    @property
    def text(self) -> str:
        return self.body.decode(self._charset(), errors="replace")

    def _charset(self) -> str:
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            return content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        return "utf-8"


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def _throttle(url: str) -> None:
    """Waits for this domain's next free slot. Long waits are handed back
    to the job pool instead of blocking a worker thread."""
    redis = get_redis()
    interval_ms = int(settings.CRAWL_DOMAIN_INTERVAL_SECONDS * 1000)
    wait_ms = int(
        redis.eval(_THROTTLE_LUA, 1, f"crawl:next:{_origin(url)}", int(time.time() * 1000), interval_ms)
    )
    if wait_ms > 15_000:
        raise Reschedule(wait_ms / 1000, f"domain throttle for {_origin(url)}")
    if wait_ms > 0:
        time.sleep(wait_ms / 1000)


def _robots_parser(url: str) -> robotparser.RobotFileParser | None:
    """Parsed robots.txt for url's origin, or None when it allows all."""
    origin = _origin(url)
    redis = get_redis()
    key = f"robots:{origin}"
    cached = redis.get(key)
    if cached is None:
        try:
            response = requests.get(
                f"{origin}/robots.txt",
                headers={"User-Agent": settings.CRAWL_USER_AGENT},
                timeout=settings.CRAWL_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            # Can't tell what's allowed: back off rather than assume.
            raise Reschedule(1800, f"robots.txt unreachable for {origin}: {exc}") from exc
        if response.status_code >= 500:
            raise Reschedule(1800, f"robots.txt HTTP {response.status_code} for {origin}")
        # 4xx (no robots.txt) means everything is allowed.
        cached = response.text[:500_000] if response.status_code == 200 else ""
        redis.set(key, cached, ex=settings.ROBOTS_CACHE_HOURS * 3600)
    if not cached.strip():
        return None
    parser = robotparser.RobotFileParser()
    parser.parse(cached.splitlines())
    return parser


def robots_allowed(url: str) -> bool:
    parser = _robots_parser(url)
    return parser is None or parser.can_fetch(settings.ROBOTS_USER_AGENT, url)


def polite_get(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> HttpResult:
    if not robots_allowed(url):
        raise BlockedError(f"disallowed by robots.txt: {url}")
    _throttle(url)

    headers = {"User-Agent": settings.CRAWL_USER_AGENT, "Accept-Language": "vi,en;q=0.8"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    if extra_headers:
        headers.update(extra_headers)

    with requests.get(url, headers=headers, timeout=settings.CRAWL_TIMEOUT_SECONDS, stream=True) as response:
        resp_headers = {k.lower(): v for k, v in response.headers.items()}
        if response.status_code == 304:
            return HttpResult(url=response.url, status=304, headers=resp_headers, not_modified=True)
        if response.status_code in _BLOCK_STATUSES:
            retry_after = resp_headers.get("retry-after")
            raise BlockedError(
                f"HTTP {response.status_code} from {url}",
                http_status=response.status_code,
                retry_after=float(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        response.raise_for_status()

        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > settings.CRAWL_MAX_BYTES:
                raise ValueError(f"response larger than {settings.CRAWL_MAX_BYTES} bytes: {url}")
            chunks.append(chunk)
        result = HttpResult(url=response.url, status=response.status_code, body=b"".join(chunks), headers=resp_headers)

    head = result.body[:20_000].decode("utf-8", errors="ignore").lower()
    if any(marker in head for marker in _CAPTCHA_MARKERS) and "<item" not in head and "<entry" not in head:
        raise BlockedError(f"CAPTCHA/challenge page at {url}", http_status=result.status)
    return result
