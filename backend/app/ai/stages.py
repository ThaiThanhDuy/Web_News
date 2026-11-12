"""The two AI stages: classify (ai_fast queue) and summarize (ai_deep queue).
Each call is recorded as an enrichment of a pipeline version that pins the
prompt, schema, provider and model that produced it."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ai import prompts
from app.ai.errors import LLMInvalidOutput, LLMRateLimited
from app.ai.providers import LLMProvider, LLMResult, get_provider
from app.config import settings
from app.services.compress import condense
from app.models import Enrichment, Item, PipelineVersion

# Output caps (also the budget reservation; unused tokens are refunded).
CLASSIFY_MAX_OUTPUT = 400
SUMMARIZE_MAX_OUTPUT = 800


@dataclass
class StageResult:
    output: dict
    llm: LLMResult
    pipeline_version_id: int


def _pipeline_version(db: Session, stage: str, name: str, provider: str, model: str, system: str, schema: dict) -> int:
    sha = prompts.prompt_sha256(system, schema)
    stmt = (
        pg_insert(PipelineVersion)
        .values(stage=stage, name=name, provider=provider, model=model, prompt_sha256=sha, json_schema=schema)
        .on_conflict_do_nothing(constraint="uq_pipeline_versions")
    )
    db.execute(stmt)
    return db.execute(
        select(PipelineVersion.id).where(
            PipelineVersion.stage == stage,
            PipelineVersion.name == name,
            PipelineVersion.provider == provider,
            PipelineVersion.model == model,
            PipelineVersion.prompt_sha256 == sha,
        )
    ).scalar_one()


def _call_with_fallback(
    provider: LLMProvider, stage: str, topic_slug: str | None, **kwargs
) -> LLMResult:
    """The stage's model first; when it's rate limited (per-minute or daily
    quota), the backup models in order. Only rate limits fall through —
    other errors are the item's/config's and surface immediately."""
    shortest_wait: float | None = None
    last_error: LLMRateLimited | None = None
    for model in provider.candidates(stage, topic_slug):
        try:
            return provider.chat_json(model=model, **kwargs)
        except LLMRateLimited as exc:
            last_error = exc
            shortest_wait = exc.retry_after if shortest_wait is None else min(shortest_wait, exc.retry_after)
    raise LLMRateLimited(f"every model rate limited ({last_error})", retry_after=shortest_wait or 60)


def _content(item: Item, max_chars: int) -> str:
    """Article text cleaned and condensed locally (no tokens) to max_chars."""
    return condense(item.title, item.content or item.feed_summary or item.title, max_chars)


def _record(db: Session, item: Item, stage: str, version_id: int, output: dict, llm: LLMResult) -> None:
    db.execute(
        pg_insert(Enrichment)
        .values(
            item_id=item.id,
            pipeline_version_id=version_id,
            stage=stage,
            output=output,
            prompt_tokens=llm.prompt_tokens,
            completion_tokens=llm.completion_tokens,
            latency_ms=llm.latency_ms,
        )
        .on_conflict_do_update(
            constraint="uq_enrichments_item_version",
            set_={
                "output": output,
                "prompt_tokens": llm.prompt_tokens,
                "completion_tokens": llm.completion_tokens,
                "latency_ms": llm.latency_ms,
            },
        )
    )


def classify(db: Session, item: Item) -> StageResult:
    provider = get_provider()
    user = prompts.article_message(
        item.title,
        item.source.name,
        _content(item, settings.CLASSIFY_MAX_CONTENT_CHARS),
        settings.CLASSIFY_MAX_CONTENT_CHARS,
    )
    llm = _call_with_fallback(
        provider,
        "classify",
        None,
        system=prompts.CLASSIFY_SYSTEM,
        user=user,
        schema_name="classify",
        schema=prompts.CLASSIFY_SCHEMA,
        max_output_tokens=CLASSIFY_MAX_OUTPUT,
    )
    topic = str(llm.data.get("topic", "")).strip().lower()
    if topic not in prompts.TOPIC_SLUGS:
        topic = "khac"
    sentiment = str(llm.data.get("sentiment", "neutral")).strip().lower()
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"
    try:
        relevance = max(0, min(100, int(llm.data.get("relevance", 50))))
    except (TypeError, ValueError):
        relevance = 50
    output = {"topic": topic, "relevance": relevance, "sentiment": sentiment}

    version_id = _pipeline_version(
        db, "classify", prompts.CLASSIFY_VERSION, provider.name, llm.model, prompts.CLASSIFY_SYSTEM, prompts.CLASSIFY_SCHEMA
    )
    _record(db, item, "classify", version_id, output, llm)
    return StageResult(output, llm, version_id)


def summarize(db: Session, item: Item, topic_slug: str | None) -> StageResult:
    provider = get_provider()
    user = prompts.article_message(
        item.title, item.source.name, _content(item, settings.SUMMARIZE_MAX_CONTENT_CHARS), settings.SUMMARIZE_MAX_CONTENT_CHARS
    )
    llm = _call_with_fallback(
        provider,
        "summarize",
        topic_slug,
        system=prompts.SUMMARIZE_SYSTEM,
        user=user,
        schema_name="summarize",
        schema=prompts.SUMMARIZE_SCHEMA,
        max_output_tokens=SUMMARIZE_MAX_OUTPUT,
    )
    # Strict mode guarantees the shape, not the content — validate it.
    bullets = [str(b).strip() for b in llm.data.get("summary_bullets") or [] if str(b).strip()][:3]
    takeaway = str(llm.data.get("one_line_takeaway") or "").strip()
    keywords = [str(k).strip() for k in llm.data.get("keywords") or [] if str(k).strip()][:5]
    if not bullets or not takeaway:
        raise LLMInvalidOutput(f"empty summary for item {item.id}: {llm.data}")
    sentiment = str(llm.data.get("sentiment", "neutral")).strip().lower()
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"
    try:
        relevance = max(0, min(100, int(llm.data.get("relevance", 50))))
    except (TypeError, ValueError):
        relevance = 50
    output = {
        "summary_bullets": bullets,
        "one_line_takeaway": takeaway[:500],
        "keywords": keywords,
        # Used for items that skipped classify (single-topic sources).
        "relevance": relevance,
        "sentiment": sentiment,
        # Secondary topics (deduplicated, valid slugs, the primary one removed).
        "related_topics": [
            slug
            for slug in dict.fromkeys(str(t).strip().lower() for t in llm.data.get("related_topics") or [])
            if slug in prompts.RELATED_TOPIC_SLUGS and slug != topic_slug
        ][:3],
    }

    version_id = _pipeline_version(
        db,
        "summarize",
        prompts.SUMMARIZE_VERSION,
        provider.name,
        llm.model,
        prompts.SUMMARIZE_SYSTEM,
        prompts.SUMMARIZE_SCHEMA,
    )
    _record(db, item, "summarize", version_id, output, llm)
    return StageResult(output, llm, version_id)
