"""Creates / upgrades the schema (Alembic) and syncs sources + topics.
Safe to run repeatedly; run it after every pull that adds a migration.

Usage (from backend/, with the venv active):
    python scripts/init_db.py
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.seed import seed_sources_and_topics  # noqa: E402


def main() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(config, "head")
    with SessionLocal() as db:
        seed_sources_and_topics(db)
    print("Database ready: migrations applied, sources/topics synced.")


if __name__ == "__main__":
    main()
