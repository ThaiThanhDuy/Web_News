"""Local topic classifier (CPU, no tokens): k-nearest neighbours over the
sentence embeddings every item already has, trained on topics the AI
assigned (latest classify enrichment) and on single-topic source labels.

Self-gating — it only takes decisions away from the AI once it has proven
itself: maint.local_classifier_eval runs a leave-one-out evaluation on all
labeled items (tech sources only, the ones that would otherwise cost a
classify call) and switches the classifier on only while its keep/drop
decisions (followed topic vs not) are right ≥ LOCAL_CLASSIFY_MIN_ACCURACY
of the time over ≥ LOCAL_CLASSIFY_MIN_DECIDED decisions. Items it predicts
as "khac" or with low confidence always go to the AI.

Items the classifier labels itself are never used as training data (they
have no classify enrichment), so it can't reinforce its own mistakes.
"""

import json
import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

GATE_KEY = "local_classifier:gate"
_CACHE_TTL_SECONDS = 600


@dataclass
class Prediction:
    topic: str
    confidence: float  # weighted vote share of the top topic
    mean_similarity: float


@dataclass
class _Training:
    ids: np.ndarray
    vectors: np.ndarray  # L2-normalized
    labels: np.ndarray
    tech: np.ndarray  # from a tech (classify-needing) source
    loaded_at: float


_cache: _Training | None = None
_lock = threading.Lock()


def _load(db: Session) -> _Training:
    rows = db.execute(
        text(
            """
            SELECT i.id, i.embedding::text AS embedding, s.default_topic IS NULL AS tech,
                   COALESCE(
                       (SELECT e.output->>'topic' FROM enrichments e
                        WHERE e.item_id = i.id AND e.stage = 'classify'
                        ORDER BY e.created_at DESC LIMIT 1),
                       s.default_topic) AS label
            FROM items i JOIN sources s ON s.id = i.source_id
            WHERE i.embedding IS NOT NULL
            """
        )
    ).all()
    rows = [r for r in rows if r.label]
    if not rows:
        empty = np.zeros((0, settings.EMBEDDING_DIM), dtype=np.float32)
        return _Training(np.array([]), empty, np.array([]), np.array([]), time.time())
    vectors = np.array([json.loads(r.embedding) for r in rows], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
    return _Training(
        np.array([r.id for r in rows]),
        vectors,
        np.array([r.label for r in rows]),
        np.array([r.tech for r in rows]),
        time.time(),
    )


def _training(db: Session) -> _Training:
    global _cache
    with _lock:
        if _cache is None or time.time() - _cache.loaded_at > _CACHE_TTL_SECONDS:
            _cache = _load(db)
        return _cache


def _vote(similarities: np.ndarray, labels: np.ndarray) -> Prediction | None:
    k = min(settings.LOCAL_CLASSIFY_K, len(similarities))
    if k == 0:
        return None
    top = np.argpartition(-similarities, k - 1)[:k]
    votes: dict[str, float] = {}
    for j in top:
        votes[labels[j]] = votes.get(labels[j], 0.0) + max(float(similarities[j]), 0.0)
    total = sum(votes.values())
    if total <= 0:
        return None
    topic, weight = max(votes.items(), key=lambda kv: kv[1])
    return Prediction(topic, weight / total, float(similarities[top].mean()))


def _confident(p: Prediction | None) -> bool:
    return (
        p is not None
        and p.topic != "khac"
        and p.confidence >= settings.LOCAL_CLASSIFY_MIN_SHARE
        and p.mean_similarity >= settings.LOCAL_CLASSIFY_MIN_SIMILARITY
    )


def gate_status() -> dict:
    try:
        raw = get_redis().get(GATE_KEY)
        return json.loads(raw) if raw else {"active": False, "reason": "not evaluated yet"}
    except Exception:
        return {"active": False, "reason": "redis unavailable"}


def predict(db: Session, item_id: int, embedding) -> Prediction | None:
    """A confident local topic, or None (→ ask the AI)."""
    if settings.LOCAL_CLASSIFY != "auto" or embedding is None or not gate_status().get("active"):
        return None
    data = _training(db)
    if len(data.labels) == 0:
        return None
    vector = np.asarray(embedding, dtype=np.float32)
    vector /= np.linalg.norm(vector) + 1e-9
    similarities = data.vectors @ vector
    similarities[data.ids == item_id] = -1.0  # never vote for itself
    prediction = _vote(similarities, data.labels)
    return prediction if _confident(prediction) else None


def evaluate(db: Session) -> dict:
    """Leave-one-out evaluation; stores and returns the gate status."""
    global _cache
    with _lock:
        _cache = _load(db)
        data = _cache
    followed = set(settings.followed_topics)
    targets = np.where(data.tech)[0]
    decided = correct = keep_drop_ok = 0
    if len(targets):
        sims = data.vectors[targets] @ data.vectors.T
        for row, i in enumerate(targets):
            s = sims[row].copy()
            s[i] = -1.0
            p = _vote(s, data.labels)
            if not _confident(p):
                continue
            decided += 1
            correct += p.topic == data.labels[i]
            truth_followed = not followed or data.labels[i] in followed
            keep_drop_ok += (not followed or p.topic in followed) == truth_followed
    accuracy = keep_drop_ok / decided if decided else 0.0
    active = decided >= settings.LOCAL_CLASSIFY_MIN_DECIDED and accuracy >= settings.LOCAL_CLASSIFY_MIN_ACCURACY
    status = {
        "active": bool(active and settings.LOCAL_CLASSIFY == "auto"),
        "samples": int(len(targets)),
        "decided": decided,
        "decided_share": round(decided / len(targets), 3) if len(targets) else 0.0,
        "keep_drop_accuracy": round(accuracy, 3),
        "topic_accuracy": round(correct / decided, 3) if decided else 0.0,
        "evaluated_at": time.time(),
        "reason": None
        if active
        else f"needs ≥{settings.LOCAL_CLASSIFY_MIN_DECIDED} decisions at ≥{settings.LOCAL_CLASSIFY_MIN_ACCURACY:.0%} keep/drop accuracy",
    }
    try:
        get_redis().set(GATE_KEY, json.dumps(status), ex=2 * 86400)
    except Exception:
        logger.warning("could not store local classifier gate")
    return status
