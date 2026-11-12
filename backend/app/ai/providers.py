"""LLM providers behind one interface, selected by LLM_PROVIDER.

  - GroqProvider   (default) OpenAI-compatible cloud API, strict JSON Schema
  - OllamaProvider local model — kept as an extension point; not exercised
                   while LLM_PROVIDER=groq

Adding another provider = one class with `chat_json` + an entry in
get_provider(); the pipeline stages don't change.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import requests

from app.ai import budget
from app.ai.errors import LLMConfigError, LLMInvalidOutput, LLMRateLimited, LLMTransientError
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    data: dict
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int


class LLMProvider(Protocol):
    name: str

    def model_for(self, stage: str, topic_slug: str | None = None) -> str: ...

    def candidates(self, stage: str, topic_slug: str | None = None) -> list[str]: ...

    def chat_json(
        self, *, model: str, system: str, user: str, schema_name: str, schema: dict, max_output_tokens: int
    ) -> LLMResult: ...


def _retry_after(response: requests.Response, default: float) -> float:
    try:
        return max(1.0, float(response.headers.get("retry-after", default)))
    except ValueError:
        return default


class GroqProvider:
    name = "groq"

    def model_for(self, stage: str, topic_slug: str | None = None) -> str:
        if stage == "classify":
            return settings.CLASSIFY_MODEL
        if topic_slug and topic_slug in settings.summarize_model_by_topic:
            return settings.summarize_model_by_topic[topic_slug]
        return settings.SUMMARIZE_MODEL

    def candidates(self, stage: str, topic_slug: str | None = None) -> list[str]:
        """The stage's own model first, then the backups (deduplicated)."""
        return list(dict.fromkeys([self.model_for(stage, topic_slug), *settings.groq_fallback_models]))

    def chat_json(
        self, *, model: str, system: str, user: str, schema_name: str, schema: dict, max_output_tokens: int
    ) -> LLMResult:
        if not settings.GROQ_API_KEY:
            raise LLMConfigError("GROQ_API_KEY is not set in backend/.env")

        estimate = budget.estimate_tokens(system, user, max_output=max_output_tokens)
        budget.reserve(model, estimate)  # raises LLMRateLimited when spent

        started = time.monotonic()
        try:
            response = requests.post(
                f"{settings.GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": 0.3,
                    "max_completion_tokens": max_output_tokens,
                    "reasoning_effort": settings.reasoning_effort_by_model.get(model, settings.LLM_REASONING_EFFORT),
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                    },
                },
                timeout=120,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            budget.refund(model, estimate)
            raise LLMTransientError(f"Groq unreachable: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        status = response.status_code
        if status != 200:
            budget.refund(model, estimate)
        if status in (401, 403):
            raise LLMConfigError(f"Groq rejected the API key (HTTP {status}): {response.text[:200]}")
        if status == 404:
            raise LLMConfigError(f"Groq model {model!r} not available (HTTP 404): {response.text[:200]}")
        if status == 429:
            raise LLMRateLimited(f"Groq 429 for {model}: {response.text[:200]}", retry_after=_retry_after(response, 60))
        if status >= 500:
            raise LLMTransientError(f"Groq HTTP {status}")
        if status != 200:
            # 400 json_validate_failed and similar: the model's answer for
            # this input didn't validate.
            raise LLMInvalidOutput(f"Groq HTTP {status}: {response.text[:300]}")

        body = response.json()
        usage = body.get("usage") or {}
        prompt_tokens, completion_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if usage.get("total_tokens") is not None:
            budget.settle(model, estimate, int(usage["total_tokens"]))
        try:
            content = body["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMInvalidOutput(f"unparseable Groq response: {str(body)[:300]}") from exc
        if not isinstance(data, dict):
            raise LLMInvalidOutput("Groq response is not a JSON object")
        return LLMResult(data, model, prompt_tokens, completion_tokens, latency_ms)


class OllamaProvider:
    """Local inference through Ollama (./start-ollama.sh). One model for
    every stage (OLLAMA_MODEL); no token budget — speed is bounded by this
    machine's CPU/GPU instead."""

    name = "ollama"

    def model_for(self, stage: str, topic_slug: str | None = None) -> str:
        return settings.OLLAMA_MODEL

    def candidates(self, stage: str, topic_slug: str | None = None) -> list[str]:
        return [settings.OLLAMA_MODEL]

    def chat_json(
        self, *, model: str, system: str, user: str, schema_name: str, schema: dict, max_output_tokens: int
    ) -> LLMResult:
        started = time.monotonic()
        try:
            response = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "format": schema,  # Ollama accepts a JSON Schema here
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": max_output_tokens},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
                # CPU inference of a 14b model can take minutes per article.
                timeout=900,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise LLMTransientError(f"Ollama unreachable/slow: {exc}") from exc
        if response.status_code >= 500:
            raise LLMTransientError(f"Ollama HTTP {response.status_code}")
        if response.status_code == 404:
            raise LLMConfigError(f"Ollama model {model!r} not pulled: {response.text[:200]}")
        if response.status_code != 200:
            raise LLMInvalidOutput(f"Ollama HTTP {response.status_code}: {response.text[:300]}")

        body = response.json()
        try:
            data = json.loads(body["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LLMInvalidOutput(f"unparseable Ollama response: {str(body)[:300]}") from exc
        if not isinstance(data, dict):
            raise LLMInvalidOutput("Ollama response is not a JSON object")
        return LLMResult(
            data,
            model,
            body.get("prompt_eval_count"),
            body.get("eval_count"),
            int((time.monotonic() - started) * 1000),
        )


def get_provider() -> LLMProvider:
    provider = settings.LLM_PROVIDER.strip().lower()
    if provider == "groq":
        return GroqProvider()
    if provider == "ollama":
        return OllamaProvider()
    raise LLMConfigError(f"Unknown LLM_PROVIDER={settings.LLM_PROVIDER!r} (expected 'groq' or 'ollama')")
