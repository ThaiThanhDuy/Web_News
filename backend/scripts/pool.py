"""Inspect and steer the job pool.

Usage (from backend/, with the venv active):
    python scripts/pool.py status              queues, items by status, sources, AI token usage
    python scripts/pool.py fetch-now [slug]    make every (or one) source due right now
    python scripts/pool.py requeue-dead        move dead jobs back to the queue
    python scripts/pool.py rerun STAGE         re-run classify|summarize for every enriched item
                                               (after changing a prompt or model)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, text, update  # noqa: E402

from app.ai import budget  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Item, ItemStatus, Source  # noqa: E402
from app.pipeline.steps import enqueue_next  # noqa: E402


def status() -> None:
    with SessionLocal() as db:
        print("Jobs (queue / status / count / oldest due):")
        rows = db.execute(
            text(
                """
                SELECT queue, status, count(*) AS n,
                       to_char(now() - min(run_at) FILTER (WHERE status = 'queued' AND run_at <= now()),
                               'HH24:MI:SS') AS waiting
                FROM jobs WHERE status <> 'done' OR finished_at > now() - interval '1 hour'
                GROUP BY queue, status ORDER BY queue, status
                """
            )
        ).all()
        for r in rows:
            print(f"  {r.queue:12} {r.status:8} {r.n:6}   {'oldest due ' + r.waiting if r.waiting else ''}")
        if not rows:
            print("  (empty)")

        dead = db.execute(
            text("SELECT kind, left(last_error, 120) FROM jobs WHERE status = 'dead' ORDER BY finished_at DESC LIMIT 5")
        ).all()
        if dead:
            print("\nLatest dead jobs:")
            for kind, err in dead:
                print(f"  {kind}: {(err or '').splitlines()[0] if err else ''}")

        print("\nItems by status:")
        for st, n in db.execute(select(Item.status, func.count()).group_by(Item.status).order_by(Item.status)):
            print(f"  {st:12} {n}")

        print("\nSources:")
        for s in db.execute(select(Source).order_by(Source.slug)).scalars():
            state = "paused" if s.paused_until else ("on" if s.is_active else "off")
            print(
                f"  {s.slug:20} {state:6} next {s.next_run_at:%H:%M} UTC  fails={s.consecutive_failures}"
                f"{'  last error: ' + s.last_error[:80] if s.last_error else ''}"
            )

    if settings.LLM_PROVIDER == "groq":
        print("\nGroq tokens today (UTC):")
        for model in sorted({settings.CLASSIFY_MODEL, settings.SUMMARIZE_MODEL, *settings.summarize_model_by_topic.values(), *settings.groq_fallback_models}):
            print(f"  {model:30} {budget.used_today(model)}/{settings.GROQ_DAILY_TOKEN_CAP}")


def fetch_now(slug: str | None) -> None:
    with SessionLocal() as db:
        stmt = update(Source).values(next_run_at=func.now(), paused_until=None)
        if slug:
            stmt = stmt.where(Source.slug == slug)
        n = db.execute(stmt).rowcount
        db.commit()
    print(f"{n} source(s) due now — the scheduler picks them up within {settings.SCHEDULER_TICK_SECONDS}s.")


def requeue_dead() -> None:
    with SessionLocal() as db:
        n = db.execute(
            text(
                """
                UPDATE jobs SET status = 'queued', attempts = 0, run_at = now(), finished_at = NULL, updated_at = now()
                WHERE status = 'dead'
                  AND (dedupe_key IS NULL OR NOT EXISTS (
                        SELECT 1 FROM jobs j2 WHERE j2.dedupe_key = jobs.dedupe_key
                          AND j2.status IN ('queued', 'running')))
                """
            )
        ).rowcount
        db.commit()
    print(f"{n} dead job(s) re-queued.")


def rerun(stage: str) -> None:
    target = {"classify": ItemStatus.READY, "summarize": ItemStatus.CLASSIFIED}.get(stage)
    if target is None:
        sys.exit("stage must be classify or summarize")
    with SessionLocal() as db:
        items = db.execute(select(Item).where(Item.status == ItemStatus.ENRICHED)).scalars().all()
        for item in items:
            # Leaving ENRICHED hides the item from the feed until the stage
            # has run again.
            item.status = target
            enqueue_next(db, item)
        db.commit()
    print(f"{len(items)} item(s) queued to re-run {stage} (hidden from the feed until done).")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "status":
        status()
    elif args[0] == "fetch-now":
        fetch_now(args[1] if len(args) > 1 else None)
    elif args[0] == "requeue-dead":
        requeue_dead()
    elif args[0] == "rerun" and len(args) == 2:
        rerun(args[1])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
