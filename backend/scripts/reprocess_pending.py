"""Re-runs the AI pipeline for articles that are not yet processed (including
ones that previously failed, e.g. because Ollama was unreachable).
Runs synchronously in this process via Task.apply() — no need for a running
Celery worker/beat.

Usage (from backend/, with the venv active):
    python scripts/reprocess_pending.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Article  # noqa: E402
from app.worker.tasks import process_article  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        ids = db.execute(select(Article.id).where(Article.is_processed.is_(False))).scalars().all()
    finally:
        db.close()

    print(f"Found {len(ids)} unprocessed articles. Reprocessing...")
    ok, failed = 0, 0
    for i, article_id in enumerate(ids, 1):
        # .apply() (not .run()) so the task gets a real request context —
        # process_article uses self.retry(), which requires one.
        result = process_article.apply(args=[article_id])
        if result.failed():
            print(f"  [{i}/{len(ids)}] article {article_id} failed: {result.result}")
            failed += 1
            continue

        db = SessionLocal()
        try:
            article = db.get(Article, article_id)
            if article and article.is_processed:
                ok += 1
                print(f"  [{i}/{len(ids)}] article {article_id} OK")
            else:
                failed += 1
                print(f"  [{i}/{len(ids)}] article {article_id} still failed")
        finally:
            db.close()

    print(f"Done. Success: {ok}, still failed: {failed}")


if __name__ == "__main__":
    main()
