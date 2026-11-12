import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.config import settings
from app.database import SessionLocal, engine
from app.routers import articles, dashboard, events, meta, push, search
from app.seed import seed_sources_and_topics


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is managed by Alembic, never created here.
    if not inspect(engine).has_table("items"):
        raise RuntimeError("Database schema missing — run `alembic upgrade head` in backend/ first.")
    with SessionLocal() as db:
        seed_sources_and_topics(db)
    if settings.EMBEDDINGS_ENABLED:
        # Load the embedding model in the background so the first search
        # with "related" results doesn't pay the multi-second load.
        from app.services.embeddings import warm_up

        threading.Thread(target=warm_up, name="embeddings-warmup", daemon=True).start()
    yield


app = FastAPI(title="Web News API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(articles.router)
app.include_router(push.router)
app.include_router(search.router)
app.include_router(dashboard.router)
app.include_router(events.router)


@app.get("/health")
def health():
    return {"status": "ok"}
