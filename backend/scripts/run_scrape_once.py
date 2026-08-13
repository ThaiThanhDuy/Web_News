"""Manual one-shot scrape + AI-processing run for local testing, without
needing Celery/Redis running (uses Celery's eager mode so tasks execute
synchronously in this process, exercising the exact same task code the
worker uses in production).

Usage (from backend/, with the venv active):
    python scripts/run_scrape_once.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.worker.celery_app import celery_app  # noqa: E402

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

from app.worker.tasks import scrape_all_sources  # noqa: E402


def main() -> None:
    result = scrape_all_sources.run()
    print(f"Done. New articles scraped and processed: {result['new_articles']}")


if __name__ == "__main__":
    main()
