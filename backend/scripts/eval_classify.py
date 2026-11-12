"""A/B check of the CURRENT classify prompt/model against the labels already
stored for recent items (spends tokens: ~1K per item). Run it after changing
the classify prompt, CLASSIFY_MAX_CONTENT_CHARS or CLASSIFY_MODEL, ideally
right after the daily quota resets (07:00 Vietnam time).

Usage (from backend/, with the venv active):
    python scripts/eval_classify.py [N=30]
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.ai import prompts  # noqa: E402
from app.ai.errors import LLMError, LLMInvalidOutput, LLMRateLimited  # noqa: E402
from app.ai.providers import get_provider  # noqa: E402
from app.ai.stages import CLASSIFY_MAX_OUTPUT, _content  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Item  # noqa: E402


def main(n: int) -> None:
    followed = set(settings.followed_topics)
    provider = get_provider()
    model = provider.model_for("classify")
    results = []
    with SessionLocal() as db:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT ON (i.id) i.id, e.output->>'topic' AS old
                FROM items i
                JOIN enrichments e ON e.item_id = i.id AND e.stage = 'classify'
                JOIN sources s ON s.id = i.source_id
                WHERE s.default_topic IS NULL
                ORDER BY i.id DESC, e.created_at DESC
                LIMIT :n
                """
            ),
            {"n": n},
        ).all()
        for row in rows:
            item = db.get(Item, row.id)
            user = prompts.article_message(
                item.title, item.source.name, _content(item, settings.CLASSIFY_MAX_CONTENT_CHARS),
                settings.CLASSIFY_MAX_CONTENT_CHARS,
            )
            for _ in range(5):
                try:
                    res = provider.chat_json(
                        model=model, system=prompts.CLASSIFY_SYSTEM, user=user, schema_name="classify",
                        schema=prompts.CLASSIFY_SCHEMA, max_output_tokens=CLASSIFY_MAX_OUTPUT,
                    )
                    tokens = (res.prompt_tokens or 0) + (res.completion_tokens or 0)
                    results.append((item.title, row.old, res.data.get("topic"), tokens))
                    break
                except LLMRateLimited as exc:
                    if exc.retry_after > 120:
                        print(f"Stopped: {exc}")
                        return report(results, followed)
                    time.sleep(exc.retry_after + 1)
                except LLMInvalidOutput:
                    results.append((item.title, row.old, "INVALID", 0))
                    break
                except LLMError as exc:
                    print(f"Stopped: {exc}")
                    return report(results, followed)
    report(results, followed)


def report(results, followed) -> None:
    valid = [r for r in results if r[2] != "INVALID"]
    if not valid:
        print("No results.")
        return
    same = sum(old == new for _, old, new, _ in valid)
    keep = sum((new in followed) == (old in followed) for _, old, new, _ in valid)
    print(
        f"{len(results)} items ({len(results) - len(valid)} invalid): same topic {same / len(valid):.0%}, "
        f"same keep/drop {keep / len(valid):.0%}, avg {sum(t for *_, t in valid) / len(valid):.0f} tokens/classify"
    )
    for title, old, new, _ in results:
        if old != new:
            print(f"  {old:12} -> {new:12} | {title[:80]}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
