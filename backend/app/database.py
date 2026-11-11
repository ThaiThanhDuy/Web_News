from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Sized for the worker process: one connection per worker thread plus the
# scheduler (which holds its advisory-lock connection) and the lease
# heartbeat. The API uses far fewer.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=12, max_overflow=8, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
