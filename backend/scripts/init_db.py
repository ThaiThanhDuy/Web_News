"""One-time setup: creates the pgvector extension, all tables, and seeds
sources/categories. Run this once after creating the Postgres database and
before starting the API or the Celery worker/beat.

Usage (from backend/, with the venv active):
    python scripts/init_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401  (registers tables on Base.metadata)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed_sources_and_categories  # noqa: E402


def main() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_sources_and_categories(db)
    finally:
        db.close()

    print("Database initialized: pgvector extension enabled, tables created, sources/categories seeded.")


if __name__ == "__main__":
    main()
