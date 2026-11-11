"""Worker process: N threads per queue pulling from the shared job pool.

Workers aren't assigned work — each thread claims the next due job of its
queue when it's free, so adding capacity is just running more threads or
processes (WORKER_QUEUES) with no code change.
"""

import logging
import os
import socket
import threading
import time
import traceback
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.jobs import queue as jobq
from app.jobs.errors import PermanentJobError, Reschedule

logger = logging.getLogger(__name__)

Handler = Callable[[Session, jobq.ClaimedJob], None]


class Worker:
    def __init__(self, queue_threads: dict[str, int], handlers: dict[str, Handler]):
        unknown = set(queue_threads) - set(jobq.QUEUES)
        if unknown:
            raise ValueError(f"unknown queues in WORKER_QUEUES: {sorted(unknown)}")
        self.queue_threads = queue_threads
        self.handlers = handlers
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._in_flight: dict[int, str] = {}  # job id -> owner tag
        self._in_flight_lock = threading.Lock()

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        for queue_name, count in self.queue_threads.items():
            for i in range(count):
                t = threading.Thread(
                    target=self._loop, args=(queue_name,), name=f"{queue_name}-{i}", daemon=True
                )
                t.start()
                self._threads.append(t)
        hb = threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True)
        hb.start()
        self._threads.append(hb)
        logger.info("Worker %s started: %s", self.worker_id, self.queue_threads)

    def stop(self, timeout: float = 30.0) -> None:
        """Stops claiming new jobs and waits for in-flight ones to finish.
        Anything still running after `timeout` is picked up again by the
        lease reaper."""
        self.stop_event.set()
        deadline = time.monotonic() + timeout
        for t in self._threads:
            t.join(max(0.0, deadline - time.monotonic()))

    # ---------------------------------------------------------------- loops

    def _loop(self, queue_name: str) -> None:
        idle_sleep = settings.WORKER_IDLE_POLL_SECONDS
        while not self.stop_event.is_set():
            try:
                with SessionLocal() as db:
                    jobs = jobq.claim(db, queue_name, self.worker_id, limit=1)
                    db.commit()
            except Exception:
                logger.exception("[%s] claim failed", queue_name)
                self.stop_event.wait(5)
                continue

            if not jobs:
                self.stop_event.wait(idle_sleep)
                continue
            for job in jobs:
                pause = self._run(job)
                if pause:
                    self.stop_event.wait(pause)

    def _run(self, job: jobq.ClaimedJob) -> float | None:
        """Runs one job; returns seconds this thread should pause its
        queue for (rate limits), else None."""
        handler = self.handlers.get(job.kind)
        with self._in_flight_lock:
            self._in_flight[job.id] = job.kind
        started = time.monotonic()
        db = SessionLocal()
        try:
            if handler is None:
                raise PermanentJobError(f"no handler registered for kind {job.kind!r}")
            handler(db, job)
            if jobq.mark_done(db, job.id, self.worker_id):
                db.commit()
                logger.info("done %s #%s (%.0f ms)", job.kind, job.id, (time.monotonic() - started) * 1000)
            else:
                db.rollback()
                logger.warning("lost lease on %s #%s; discarded its work", job.kind, job.id)
        except Reschedule as r:
            db.rollback()
            jobq.reschedule(db, job, self.worker_id, r.delay, r.reason)
            db.commit()
            logger.info("rescheduled %s #%s in %.0fs: %s", job.kind, job.id, r.delay, r.reason)
            if r.pause_queue:
                return r.delay
        except Exception as exc:
            db.rollback()
            permanent = isinstance(exc, PermanentJobError)
            status = jobq.mark_failed(
                db, job, self.worker_id, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", permanent=permanent
            )
            db.commit()
            log = logger.error if status == "dead" else logger.warning
            log("%s #%s failed (attempt %s/%s) -> %s: %s", job.kind, job.id, job.attempts, job.max_attempts, status, exc)
        finally:
            db.close()
            with self._in_flight_lock:
                self._in_flight.pop(job.id, None)
        return None

    def _heartbeat_loop(self) -> None:
        """Extends the lease of every in-flight job well before it expires,
        so long-running jobs aren't reaped while their worker is alive."""
        interval = max(10, settings.JOB_LEASE_SECONDS // 3)
        while not self.stop_event.wait(interval):
            with self._in_flight_lock:
                ids = list(self._in_flight)
            if not ids:
                continue
            try:
                with SessionLocal() as db:
                    jobq.extend_leases(db, ids, self.worker_id)
                    db.commit()
            except Exception:
                logger.exception("lease heartbeat failed")
