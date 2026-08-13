from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://web_news:web_news@localhost:5432/web_news"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Local model served by Ollama — see start-ollama.sh. Private, free, no
    # rate limit; speed depends entirely on this machine's CPU/GPU.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:14b-instruct"

    EMBEDDING_MODEL_NAME: str = "paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM: int = 384

    CORS_ORIGINS: str = "http://localhost:3000"

    HOTNESS_WINDOW_HOURS: int = 72
    CLUSTER_WINDOW_HOURS: int = 48
    CLUSTER_DISTANCE_THRESHOLD: float = 0.25

    # Main feed ordering: the top N hottest articles published within the
    # last FEED_HOT_WINDOW_HOURS lead the feed, followed by everything else
    # newest-first.
    FEED_HOT_COUNT: int = 5
    FEED_HOT_WINDOW_HOURS: int = 48

    SCRAPE_INTERVAL_SECONDS: int = 180
    HOTNESS_RECOMPUTE_INTERVAL_SECONDS: int = 300

    # Slower, redundant re-scan of every source (see backfill_recent_articles
    # in worker/tasks.py) that catches anything the frequent scrape above
    # missed due to a transient failure, bounded to the last N days so it
    # doesn't try to resurrect already-stale content.
    BACKFILL_INTERVAL_SECONDS: int = 600
    BACKFILL_MAX_AGE_DAYS: int = 7

    # Articles older than this are dropped entirely — from every listing
    # query immediately, and from the database itself via the periodic
    # cleanup_old_articles task.
    ARTICLE_RETENTION_DAYS: int = 14
    CLEANUP_INTERVAL_SECONDS: int = 3600

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
