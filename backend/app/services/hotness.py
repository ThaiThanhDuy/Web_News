"""News ranking score (0-100):

    S = 100 · Σ wᵢ·xᵢ / Σ wᵢ   over the components that are available

  R  relevance from the classify stage (0-100 → 0..1)              w 0.25
  F  freshness e^(−λ·Δt), λ = ln(2)/12h (12-hour half-life)         w 0.30
  T  source trust (sources.trust, 0..1)                            w 0.10
  C  coverage: log(1+C)/log(1+5), C = sources covering the story   w 0.10
  K  keyword trend: heat of the item's hottest keyword (0..1)       w 0.15
  E  engagement (0..1, 0.5 = typical): reader clicks vs what its
     feed positions predict, and/or YouTube views per hour          w 0.10

E is left out (its weight redistributed) while it isn't measurable: no
YouTube counters, and the site below ENGAGEMENT_MIN_DAILY_IMPRESSIONS.
Weights are starting values to tune on real data.
"""

import math
from datetime import datetime, timezone

HALF_LIFE_HOURS = 12.0
LAMBDA = math.log(2) / HALF_LIFE_HOURS
C_MAX = 5

WEIGHTS = {"R": 0.25, "F": 0.30, "T": 0.10, "C": 0.10, "K": 0.15, "E": 0.10}


def compute_hotness(
    *,
    published_at: datetime,
    relevance: float | None,
    trust: float | None,
    cluster_source_count: int,
    trend: float | None = None,
    engagement: float | None = None,
    now: datetime | None = None,
) -> float:
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - published_at).total_seconds() / 3600)

    parts = {
        "R": (relevance if relevance is not None else 50.0) / 100,
        "F": math.exp(-LAMBDA * hours),
        "T": trust if trust is not None else 0.5,
        "C": min(1.0, math.log1p(max(1, cluster_source_count)) / math.log1p(C_MAX)),
        "K": max(0.0, min(1.0, trend or 0.0)),
    }
    if engagement is not None:
        parts["E"] = max(0.0, min(1.0, engagement))

    total_weight = sum(WEIGHTS[k] for k in parts)
    score = sum(WEIGHTS[k] * v for k, v in parts.items()) / total_weight
    return round(100 * score, 2)
