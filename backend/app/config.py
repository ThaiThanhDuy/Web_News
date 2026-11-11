import json
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://web_news:web_news@localhost:5432/web_news"
    # Redis is no longer a job queue: it only holds rate-limit state (Groq
    # token buckets / daily token counters, per-domain crawl spacing,
    # robots.txt cache). The job pool itself lives in Postgres (`jobs`).
    REDIS_URL: str = "redis://localhost:6379/0"

    # ------------------------------------------------------------------ AI
    # Which backend runs the AI pipeline: "groq" (cloud API, needs
    # GROQ_API_KEY) or "ollama" (local model, see start-ollama.sh — kept as
    # an extension point, not the default).
    LLM_PROVIDER: str = "groq"

    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    # Model per pipeline stage. Both default to gpt-oss-20b: slower to drain
    # a backlog on the free tier (both stages share one model's quota), but
    # nothing is dropped — every item that passes the rule filter gets both
    # a classification and a full summary.
    CLASSIFY_MODEL: str = "openai/gpt-oss-20b"
    SUMMARIZE_MODEL: str = "openai/gpt-oss-20b"
    # Optional per-topic override for the summarize stage, as JSON, e.g.
    # {"ai": "openai/gpt-oss-120b"}. Topics not listed use SUMMARIZE_MODEL.
    SUMMARIZE_MODEL_BY_TOPIC: str = ""
    # gpt-oss models "think" before answering; "low" cut completion tokens
    # ~5x in testing with no visible quality loss for these tasks.
    LLM_REASONING_EFFORT: str = "low"
    # Groq limits are per model. Free tier: 8K tokens/minute, 200K/day.
    # The daily cap is kept a bit under Groq's own so we stop *before* 429s.
    GROQ_TPM_LIMIT: int = 8000
    GROQ_DAILY_TOKEN_CAP: int = 160000

    # Local model served by Ollama — see start-ollama.sh. Used for every
    # stage when LLM_PROVIDER=ollama.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:14b-instruct"

    # Characters of article body sent to each stage.
    CLASSIFY_MAX_CONTENT_CHARS: int = 2000
    SUMMARIZE_MAX_CONTENT_CHARS: int = 4000
    # Items classified below this relevance (0-100) skip summarization.
    # 0 = summarize everything ("đầy đủ dữ liệu").
    AI_MIN_RELEVANCE: int = 0

    # ---------------------------------------------------------- embeddings
    # Sentence-transformers model for same-story clustering. Needs ~0.5-1GB
    # RAM (torch); set EMBEDDINGS_ENABLED=false on a small VPS — exact
    # (SHA-256) and near-duplicate (SimHash) detection still run without it.
    EMBEDDINGS_ENABLED: bool = True
    EMBEDDING_MODEL_NAME: str = "paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM: int = 384
    CLUSTER_WINDOW_HOURS: int = 48
    CLUSTER_DISTANCE_THRESHOLD: float = 0.25
    # Search "related" results: max cosine distance between the query's
    # embedding and an item's (needs EMBEDDINGS_ENABLED; the API process
    # then loads the embedding model too, ~0.5GB).
    SEARCH_RELATED_MAX_DISTANCE: float = 0.5

    # ------------------------------------------------------------- filters
    MIN_TITLE_CHARS: int = 10
    MIN_CONTENT_CHARS: int = 80
    # Comma-separated, case-insensitive; matched against title + content.
    BLOCKED_KEYWORDS: str = ""
    SIMHASH_MAX_DISTANCE: int = 3
    NEAR_DUP_WINDOW_HOURS: int = 48

    # ------------------------------------------------------------ crawling
    CRAWL_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    # User-agent token evaluated against robots.txt rules.
    ROBOTS_USER_AGENT: str = "TechDigestBot"
    CRAWL_TIMEOUT_SECONDS: int = 20
    CRAWL_MAX_BYTES: int = 5_000_000
    # Minimum spacing between two requests to the same domain (shared by all
    # worker processes through Redis) — effectively 1 request at a time.
    CRAWL_DOMAIN_INTERVAL_SECONDS: float = 2.0
    ROBOTS_CACHE_HOURS: int = 24
    SOURCE_MAX_CONSECUTIVE_FAILURES: int = 5
    SOURCE_PAUSE_HOURS: int = 6
    # YouTube Data API v3 key for the youtube_api connector (YouTube's
    # robots.txt forbids crawling the channel RSS feeds).
    YOUTUBE_API_KEY: str = ""
    RAW_DATA_DIR: str = "data/raw"
    RAW_RETENTION_DAYS: int = 7

    # ---------------------------------------------------------- job pool
    # "queue:threads" pairs this worker process serves.
    WORKER_QUEUES: str = "fetch:2,parse:1,filter:1,ai_fast:1,ai_deep:1,deliver:1,maintenance:1"
    JOB_LEASE_SECONDS: int = 300
    JOB_MAX_ATTEMPTS: int = 6
    WORKER_IDLE_POLL_SECONDS: float = 2.0
    SCHEDULER_TICK_SECONDS: int = 10
    JOB_DONE_RETENTION_DAYS: int = 7
    JOB_DEAD_RETENTION_DAYS: int = 30
    FETCH_RUN_RETENTION_DAYS: int = 90

    # ------------------------------------------------------ ranking / feed
    HOTNESS_WINDOW_HOURS: int = 72
    FEED_HOT_COUNT: int = 5
    FEED_HOT_WINDOW_HOURS: int = 48
    HOTNESS_RECOMPUTE_INTERVAL_SECONDS: int = 300
    ARTICLE_RETENTION_DAYS: int = 14
    CLEANUP_INTERVAL_SECONDS: int = 3600
    RECONCILE_INTERVAL_SECONDS: int = 300

    # ------------------------------------------------------------ web push
    # Generate with: python scripts/generate_vapid_keys.py
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    # Contact for push services: "mailto:you@domain" or an https URL.
    VAPID_SUBJECT: str = ""
    # Only items at least this relevant (0-100) are pushed instantly.
    PUSH_MIN_RELEVANCE: int = 60
    # Items older than this when they finish processing aren't pushed (so a
    # backlog catching up doesn't flood phones with old news).
    PUSH_MAX_ITEM_AGE_HOURS: int = 6
    PUSH_MAX_PER_HOUR: int = 4
    PUSH_TTL_SECONDS: int = 6 * 3600

    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def blocked_keywords(self) -> list[str]:
        return [k.strip().lower() for k in self.BLOCKED_KEYWORDS.split(",") if k.strip()]

    @property
    def summarize_model_by_topic(self) -> dict[str, str]:
        if not self.SUMMARIZE_MODEL_BY_TOPIC.strip():
            return {}
        data = json.loads(self.SUMMARIZE_MODEL_BY_TOPIC)
        return {str(k): str(v) for k, v in data.items()}

    @property
    def worker_queue_threads(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for part in self.WORKER_QUEUES.split(","):
            part = part.strip()
            if not part:
                continue
            name, _, count = part.partition(":")
            result[name.strip()] = int(count) if count else 1
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
