"""Re-runs AI category classification (only) for every already-processed,
non-duplicate article, using the improved category rules in services/llm.py.
Much cheaper per-article than a full reprocess since it only asks the model
for the category, not the summary/keywords/sentiment too.

Usage (from backend/, with the venv active):
    python scripts/reclassify_categories.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Article, Category  # noqa: E402
from app.services.llm import TransientLLMError, classify_category  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        article_ids = list(
            db.execute(
                select(Article.id).where(Article.is_processed.is_(True), Article.is_duplicate.is_(False))
            ).scalars().all()
        )
        categories_by_slug = {c.slug: c.id for c in db.execute(select(Category)).scalars().all()}
    finally:
        db.close()

    print(f"Reclassifying {len(article_ids)} articles...")
    changed = 0
    failed = 0

    for i, article_id in enumerate(article_ids, 1):
        db = SessionLocal()
        try:
            article = db.get(Article, article_id)
            if article is None:
                continue

            content = article.raw_content or article.title
            new_slug = None
            for attempt in range(5):
                try:
                    new_slug = classify_category(article.title, content)
                    break
                except TransientLLMError as exc:
                    wait = exc.retry_after or 30
                    print(f"  rate limited, waiting {wait:.0f}s (attempt {attempt + 1}/5)...")
                    time.sleep(wait)

            if new_slug is None:
                failed += 1
                print(f"  [{i}/{len(article_ids)}] article {article_id} failed")
                continue

            old_slug = article.category.slug if article.category else None
            if new_slug != old_slug:
                article.category_id = categories_by_slug[new_slug]
                changed += 1
                print(f"  [{i}/{len(article_ids)}] {article_id}: {old_slug} -> {new_slug}")
            db.commit()
        finally:
            db.close()

    unchanged = len(article_ids) - changed - failed
    print(f"Done. Changed: {changed}, unchanged: {unchanged}, failed: {failed}")


if __name__ == "__main__":
    main()
