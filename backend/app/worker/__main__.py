"""Worker process: `python -m app.worker` (from backend/, venv active).

Runs the job-pool threads for the queues listed in WORKER_QUEUES
("queue:threads,..."), plus the scheduler (only one process in the whole
deployment actually schedules — see app/jobs/scheduler.py). Ctrl+C / SIGTERM
stops claiming new jobs and lets in-flight ones finish.

Examples:
    python -m app.worker                                  # every queue
    WORKER_QUEUES=ai_fast:1,ai_deep:1 python -m app.worker  # AI-only worker
"""

import logging
import signal
import sys
import threading

from app.config import settings
from app.database import SessionLocal
from app.jobs.runner import Worker
from app.jobs.scheduler import Scheduler
from app.pipeline import HANDLERS
from app.seed import seed_sources_and_topics


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    with SessionLocal() as db:
        seed_sources_and_topics(db)

    worker = Worker(settings.worker_queue_threads, HANDLERS)
    scheduler = Scheduler(worker.stop_event)
    stopped = threading.Event()

    def shutdown(signum, _frame):
        if stopped.is_set():
            return
        stopped.set()
        logging.info("Received %s, finishing in-flight jobs...", signal.Signals(signum).name)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    worker.start()
    scheduler.start()
    stopped.wait()
    worker.stop(timeout=60)
    scheduler.join(timeout=5)
    logging.info("Worker stopped.")


if __name__ == "__main__":
    main()
