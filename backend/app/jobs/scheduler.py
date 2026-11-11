"""Creates jobs on a timetable: one `fetch.source` job per source whose
`next_run_at` is due, plus the periodic maintenance jobs.

Every worker process runs this thread, but only the one holding a Postgres
advisory lock acts (leader election), so running several workers — e.g. a
second VPS — never double-schedules. If the leader dies, its connection
closes, the lock is released, and another process takes over.
"""

import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.config import settings
from app.database import SessionLocal, engine
from app.jobs.queue import enqueue
from app.models import Source

logger = logging.getLogger(__name__)

SCHEDULER_LOCK_KEY = 7_340_211  # arbitrary, app-wide constant

# kind -> interval in seconds
PERIODIC_JOBS: dict[str, int] = {
    "maint.reap": 60,
    "maint.hotness": settings.HOTNESS_RECOMPUTE_INTERVAL_SECONDS,
    "maint.reconcile": settings.RECONCILE_INTERVAL_SECONDS,
    "maint.cleanup": settings.CLEANUP_INTERVAL_SECONDS,
}


class Scheduler:
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self._last_enqueued: dict[str, float] = {}
        self._thread = threading.Thread(target=self._run, name="scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float) -> None:
        self._thread.join(timeout)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                with engine.connect() as lock_conn:
                    got = lock_conn.execute(
                        text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY}
                    ).scalar()
                    lock_conn.commit()
                    if not got:
                        # Another process is leader; check again later.
                        self.stop_event.wait(30)
                        continue
                    logger.info("Scheduler: this process is the leader")
                    try:
                        while not self.stop_event.is_set():
                            self._tick()
                            lock_conn.execute(text("SELECT 1"))  # keep the lock's session alive
                            lock_conn.commit()
                            self.stop_event.wait(settings.SCHEDULER_TICK_SECONDS)
                    finally:
                        lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEDULER_LOCK_KEY})
                        lock_conn.commit()
            except Exception:
                logger.exception("Scheduler error; retrying in 15s")
                self.stop_event.wait(15)

    def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            due = db.execute(
                select(Source)
                .where(
                    Source.is_active.is_(True),
                    Source.next_run_at <= now,
                    (Source.paused_until.is_(None)) | (Source.paused_until <= now),
                )
                .with_for_update(skip_locked=True)
            ).scalars().all()
            for source in due:
                enqueue(
                    db,
                    "fetch",
                    "fetch.source",
                    {"source_id": source.id},
                    dedupe_key=f"fetch.source:{source.id}",
                    priority=10,
                )
                # Jitter spreads sources out instead of all firing together.
                jitter = random.uniform(0, 0.1) * source.fetch_interval_minutes
                source.next_run_at = now + timedelta(minutes=source.fetch_interval_minutes + jitter)
            if due:
                logger.info("Scheduler: enqueued fetch for %s", ", ".join(s.slug for s in due))

            mono = time.monotonic()
            for kind, interval in PERIODIC_JOBS.items():
                last = self._last_enqueued.get(kind)
                if last is not None and mono - last < interval:
                    continue
                enqueue(db, "maintenance", kind, {}, dedupe_key=f"periodic:{kind}", priority=10, max_attempts=3)
                self._last_enqueued[kind] = mono
            db.commit()
