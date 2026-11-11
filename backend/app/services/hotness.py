"""News ranking score:

    S = w_r·R + w_f·e^(−λ·Δt) + w_t·T + w_c·log(1+C) / log(1+C_max)

  R   relevance from the classify stage (0-100 → 0..1)
  Δt  hours since publication, λ = ln(2)/12 (12-hour half-life)
  T   source trust (sources.trust, 0..1)
  C   number of distinct sources covering the story (cluster size),
      normalized so C_max sources = 1

Scaled to 0-100. Weights are starting values to tune on real data.
"""

import math
from datetime import datetime, timezone

HALF_LIFE_HOURS = 12.0
LAMBDA = math.log(2) / HALF_LIFE_HOURS
C_MAX = 5

W_RELEVANCE = 0.30
W_FRESHNESS = 0.40
W_TRUST = 0.10
W_COVERAGE = 0.20


def compute_hotness(
    *,
    published_at: datetime,
    relevance: float | None,
    trust: float | None,
    cluster_source_count: int,
    now: datetime | None = None,
) -> float:
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - published_at).total_seconds() / 3600)

    r = (relevance if relevance is not None else 50.0) / 100
    f = math.exp(-LAMBDA * hours)
    t = trust if trust is not None else 0.5
    c = min(1.0, math.log1p(max(1, cluster_source_count)) / math.log1p(C_MAX))

    return round(100 * (W_RELEVANCE * r + W_FRESHNESS * f + W_TRUST * t + W_COVERAGE * c), 2)
