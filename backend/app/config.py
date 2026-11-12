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
    # Model per pipeline stage. Groq quotas are per model, so putting the two
    # stages on different models gives each its own daily budget: ~90 fully
    # processed items/day on the free tier, vs ~50 when both share one model
    # (then classify also yields to summarize so items still finish first).
    CLASSIFY_MODEL: str = "openai/gpt-oss-20b"
    SUMMARIZE_MODEL: str = "openai/gpt-oss-120b"
    # Optional per-topic override for the summarize stage, as JSON, e.g.
    # {"ai": "openai/gpt-oss-120b"}. Topics not listed use SUMMARIZE_MODEL.
    SUMMARIZE_MODEL_BY_TOPIC: str = ""
    # gpt-oss models "think" before answering; "low" cut completion tokens
    # ~5x in testing with no visible quality loss for these tasks.
    LLM_REASONING_EFFORT: str = "low"
    # Per-model override, JSON. qwen3 supports "none" (no thinking tokens:
    # ~25 output tokens for a classification instead of ~180).
    LLM_REASONING_EFFORT_BY_MODEL: str = '{"qwen/qwen3.8-27b": "none"}'
    # Backup models, comma-separated, tried in order when a stage's own model
    # has used up its per-minute or daily quota (each Groq model has its own
    # quota). Empty = no fallback.
    GROQ_FALLBACK_MODELS: str = "qwen/qwen3.8-27b"
    # Groq limits are per model. Free tier: 8K tokens/minute, 200K/day.
    # The daily cap is kept a bit under Groq's own so we stop *before* 429s.
    GROQ_TPM_LIMIT: int = 8000
    GROQ_DAILY_TOKEN_CAP: int = 160000

    # Local model served by Ollama — see start-ollama.sh. Used for every
    # stage when LLM_PROVIDER=ollama.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:14b-instruct"

    # Characters of article body sent to each stage, after local cleaning +
    # condensing (services/compress.py: lead + title-relevant sentences).
    # Topic is clear from the title + lead; the summary needs a bit more.
    CLASSIFY_MAX_CONTENT_CHARS: int = 1200
    SUMMARIZE_MAX_CONTENT_CHARS: int = 2400
    # Local (CPU) kNN topic classifier on embeddings: "auto" = used only while
    # its own leave-one-out evaluation shows keep/drop accuracy ≥ the minimum
    # (services/local_classifier.py); "off" = always ask the AI.
    LOCAL_CLASSIFY: str = "auto"
    LOCAL_CLASSIFY_K: int = 7
    LOCAL_CLASSIFY_MIN_SHARE: float = 0.8
    LOCAL_CLASSIFY_MIN_SIMILARITY: float = 0.35
    LOCAL_CLASSIFY_MIN_ACCURACY: float = 0.95
    LOCAL_CLASSIFY_MIN_DECIDED: int = 30
    LOCAL_CLASSIFY_EVAL_INTERVAL_SECONDS: int = 6 * 3600
    # Items older than this (by publish time) when their AI turn comes are
    # dropped instead of spending tokens on stale news. 0 = no limit.
    AI_MAX_ITEM_AGE_HOURS: int = 72
    # Items classified below this relevance (0-100) skip summarization.
    # 0 = summarize everything ("đầy đủ dữ liệu").
    AI_MIN_RELEVANCE: int = 0
    # Topics the site follows, comma-separated slugs (empty = all). Items the
    # classifier puts in any other topic are dropped right after classifying,
    # so they never cost summarize tokens, and other topics leave the menu.
    FOLLOWED_TOPICS: str = "ai,startup,phan-mem,phan-cung,kinh-te"

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

    # ------------------------------------------------- hot-news analytics
    # Keyword/search daily aggregates outlive items so trends have a baseline.
    KEYWORD_STATS_RETENTION_DAYS: int = 180
    TREND_BASELINE_DAYS: int = 28
    TRENDS_INTERVAL_SECONDS: int = 600
    YOUTUBE_STATS_INTERVAL_SECONDS: int = 1800
    # Reader engagement (anonymous counters) over this window feeds ranking...
    ENGAGEMENT_WINDOW_HOURS: int = 48
    # ...but only once the site has real traffic: below this many feed
    # impressions in the last 24h, engagement is left out of the formula.
    ENGAGEMENT_MIN_DAILY_IMPRESSIONS: int = 300
    # Per-client-IP rate limit on /api/events (the IP is never stored).
    EVENTS_MAX_PER_MINUTE: int = 300
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
    # Read-only operations dashboard (/api/dashboard/*, page /dashboard). It
    # has no login yet — set false on any deployment others can reach.
    DASHBOARD_ENABLED: bool = True

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
    def reasoning_effort_by_model(self) -> dict[str, str]:
        if not self.LLM_REASONING_EFFORT_BY_MODEL.strip():
            return {}
        return {str(k): str(v) for k, v in json.loads(self.LLM_REASONING_EFFORT_BY_MODEL).items()}

    @property
    def followed_topics(self) -> list[str]:
        return [t.strip() for t in self.FOLLOWED_TOPICS.split(",") if t.strip()]

    def follows_topic(self, slug: str | None) -> bool:
        followed = self.followed_topics
        return not followed or (slug is not None and slug in followed)

    @property
    def groq_fallback_models(self) -> list[str]:
        return [m.strip() for m in self.GROQ_FALLBACK_MODELS.split(",") if m.strip()]

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
