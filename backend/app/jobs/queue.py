"""Postgres-backed job pool primitives.

Delivery is at-least-once: a job can run again if its worker dies after
doing the work but before committing. Handlers therefore commit their side
effects in the SAME transaction that marks the job done (and enqueues the
next step), and every write is idempotent thanks to unique constraints.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Job, JobStatus

QUEUES = ("fetch", "parse", "filter", "ai_fast", "ai_deep", "deliver", "maintenance")


@dataclass
class ClaimedJob:
    id: int
    queue: str
    kind: str
    payload: dict
    attempts: int
    max_attempts: int

    @property
    def is_last_attempt(self) -> bool:
        return self.attempts >= self.max_attempts


def enqueue(
    db: Session,
    queue: str,
    kind: str,
    payload: dict | None = None,
    *,
    dedupe_key: str | None = None,
    priority: int = 100,
    run_at: datetime | None = None,
    max_attempts: int | None = None,
) -> int | None:
    """Adds a job inside the caller's transaction. Returns its id, or None
    when an active (queued/running) job with the same dedupe_key exists."""
    if queue not in QUEUES:
        raise ValueError(f"unknown queue {queue!r}")
    values = {
        "queue": queue,
        "kind": kind,
        "payload": payload or {},
        "dedupe_key": dedupe_key,
        "priority": priority,
        "max_attempts": max_attempts or settings.JOB_MAX_ATTEMPTS,
    }
    if run_at is not None:
        values["run_at"] = run_at
    stmt = (
        pg_insert(Job)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"],
            index_where=text("status IN ('queued', 'running')"),
        )
        .returning(Job.id)
    )
    return db.execute(stmt).scalar_one_or_none()


_CLAIM_SQL = text(
    """
    UPDATE jobs
    SET status = 'running',
        locked_by = :worker,
        lease_until = now() + make_interval(secs => :lease),
        attempts = attempts + 1,
        updated_at = now()
    WHERE id IN (
        SELECT id FROM jobs
        WHERE queue = :queue AND status = 'queued' AND run_at <= now()
        ORDER BY priority, run_at
        LIMIT :limit
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id, queue, kind, payload, attempts, max_attempts
    """
)


def claim(db: Session, queue: str, worker: str, limit: int = 1) -> list[ClaimedJob]:
    """Atomically takes up to `limit` due jobs. Two workers can never claim
    the same job (SKIP LOCKED). Caller must commit."""
    rows = db.execute(
        _CLAIM_SQL, {"queue": queue, "worker": worker, "lease": settings.JOB_LEASE_SECONDS, "limit": limit}
    ).all()
    return [ClaimedJob(r.id, r.queue, r.kind, r.payload, r.attempts, r.max_attempts) for r in rows]


def mark_done(db: Session, job_id: int, worker: str) -> bool:
    """In the handler's transaction. False if this worker no longer owns the
    job (lease expired and it was reclaimed) — the caller must then roll
    back, so the work is left to the new owner."""
    result = db.execute(
        text(
            """
            UPDATE jobs SET status = 'done', finished_at = now(), updated_at = now(),
                            lease_until = NULL, last_error = NULL
            WHERE id = :id AND locked_by = :worker AND status = 'running'
            """
        ),
        {"id": job_id, "worker": worker},
    )
    return result.rowcount == 1


def backoff_seconds(attempts: int) -> float:
    base = min(30 * 2 ** max(0, attempts - 1), 3600)
    return base * random.uniform(0.8, 1.2)


def mark_failed(db: Session, job: ClaimedJob, worker: str, error: str, *, permanent: bool = False) -> str:
    """Retry later with exponential backoff, or move to `dead` once out of
    attempts. Returns the new status. Caller must commit."""
    dead = permanent or job.attempts >= job.max_attempts
    status = JobStatus.DEAD if dead else JobStatus.QUEUED
    db.execute(
        text(
            """
            UPDATE jobs SET status = :status, locked_by = NULL, lease_until = NULL,
                            run_at = now() + make_interval(secs => :delay),
                            last_error = :error, updated_at = now(),
                            finished_at = CASE WHEN :status = 'dead' THEN now() END
            WHERE id = :id AND locked_by = :worker AND status = 'running'
            """
        ),
        {
            "status": status,
            "delay": 0 if dead else backoff_seconds(job.attempts),
            "error": error[:4000],
            "id": job.id,
            "worker": worker,
        },
    )
    return status


def reschedule(db: Session, job: ClaimedJob, worker: str, delay: float, reason: str) -> None:
    """Back to the queue after `delay` seconds, not counted as an attempt."""
    db.execute(
        text(
            """
            UPDATE jobs SET status = 'queued', locked_by = NULL, lease_until = NULL,
                            attempts = GREATEST(attempts - 1, 0),
                            run_at = now() + make_interval(secs => :delay),
                            last_error = :reason, updated_at = now()
            WHERE id = :id AND locked_by = :worker AND status = 'running'
            """
        ),
        {"delay": delay, "reason": reason[:4000], "id": job.id, "worker": worker},
    )


def extend_leases(db: Session, job_ids: list[int], worker: str) -> None:
    if not job_ids:
        return
    db.execute(
        text(
            """
            UPDATE jobs SET lease_until = now() + make_interval(secs => :lease), updated_at = now()
            WHERE id = ANY(:ids) AND locked_by = :worker AND status = 'running'
            """
        ),
        {"lease": settings.JOB_LEASE_SECONDS, "ids": job_ids, "worker": worker},
    )


def reap_expired_leases(db: Session) -> int:
    """Jobs whose worker died: back to `queued`, or `dead` if out of
    attempts. Caller must commit."""
    result = db.execute(
        text(
            """
            UPDATE jobs
            SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
                finished_at = CASE WHEN attempts >= max_attempts THEN now() END,
                locked_by = NULL, lease_until = NULL, run_at = now(), updated_at = now(),
                last_error = COALESCE(last_error || E'\\n', '') || 'lease expired (worker died?)'
            WHERE status = 'running' AND lease_until < now()
            """
        )
    )
    return result.rowcount


def recency_priority(published_at: datetime) -> int:
    """Lower runs first. Newest items first, so when the AI quota can't keep
    up the feed stays fresh and the backlog drains from the newest end."""
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    minutes = int(published_at.timestamp() // 60)
    return max(0, 100_000_000 - minutes)


def utc_in(seconds: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
