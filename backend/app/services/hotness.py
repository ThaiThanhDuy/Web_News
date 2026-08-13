"""Composite "hotness" score used to rank the Tin Nổi Bật feed.

hotness = 100 * (0.45 * freshness + 0.30 * cross_source_reach + 0.25 * ai_hotness)

- freshness: exponential decay based on time since publish (half-life ~12h)
- cross_source_reach: how many of the 3 tracked sources are covering the same
  story (from ArticleCluster.source_count), i.e. topic density across outlets
- ai_hotness: the LLM's own 0-100 "how newsworthy is this" estimate
"""

import math
from datetime import datetime, timezone

from app.constants import SOURCES

TOTAL_SOURCES = len(SOURCES)
FRESHNESS_HALF_LIFE_HOURS = 12.0
_DECAY_CONSTANT = FRESHNESS_HALF_LIFE_HOURS / math.log(2)

W_FRESHNESS = 0.45
W_CROSS_SOURCE = 0.30
W_AI_SCORE = 0.25


def compute_hotness(
    published_at: datetime,
    cluster_source_count: int,
    ai_hotness_score: float | None,
    now: datetime | None = None,
) -> float:
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    hours_since_publish = max(0.0, (now - published_at).total_seconds() / 3600)
    freshness = math.exp(-hours_since_publish / _DECAY_CONSTANT)

    cross_source = min(cluster_source_count / TOTAL_SOURCES, 1.0)
    ai_score = (ai_hotness_score if ai_hotness_score is not None else 50.0) / 100

    score = 100 * (W_FRESHNESS * freshness + W_CROSS_SOURCE * cross_source + W_AI_SCORE * ai_score)
    return round(score, 2)
