"""Health check for the configured AI provider: runs one sample article
through both real stages (classify + summarize) without touching the
database, and prints token usage. Never prints the API key.

    cd backend && source venv/bin/activate && python scripts/check_llm.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai import budget, prompts  # noqa: E402
from app.ai.errors import LLMConfigError, LLMError, LLMRateLimited  # noqa: E402
from app.ai.providers import get_provider  # noqa: E402
from app.ai.stages import CLASSIFY_MAX_OUTPUT, SUMMARIZE_MAX_OUTPUT  # noqa: E402
from app.config import settings  # noqa: E402

TITLE = "Apple ra mắt iPhone mới với chip A20"
CONTENT = (
    "Apple vừa công bố dòng iPhone mới trang bị chip A20, camera cải tiến và thời lượng pin dài hơn. "
    "Máy sẽ lên kệ tại Việt Nam vào tháng tới với giá từ 25 triệu đồng."
)


def run(stage: str, system: str, schema: dict, max_chars: int, max_out: int) -> bool:
    provider = get_provider()
    model = provider.model_for(stage)
    user = prompts.article_message(TITLE, "Mẫu", CONTENT, max_chars)
    started = time.monotonic()
    try:
        result = provider.chat_json(
            model=model, system=system, user=user, schema_name=stage, schema=schema, max_output_tokens=max_out
        )
    except LLMConfigError as exc:
        print(f"❌ [{stage}] Lỗi cấu hình: {exc}")
        return False
    except LLMRateLimited as exc:
        print(f"⚠️  [{stage}] Đang bị giới hạn, thử lại sau {exc.retry_after:.0f}s: {exc}")
        return False
    except LLMError as exc:
        print(f"❌ [{stage}] {type(exc).__name__}: {exc}")
        return False
    print(
        f"✅ [{stage}] {model} — {time.monotonic() - started:.1f}s, "
        f"{result.prompt_tokens} token vào / {result.completion_tokens} token ra"
    )
    print(f"   {result.data}")
    return True


def main() -> None:
    print(f"Provider: {settings.LLM_PROVIDER}")
    ok = run("classify", prompts.CLASSIFY_SYSTEM, prompts.CLASSIFY_SCHEMA, settings.CLASSIFY_MAX_CONTENT_CHARS, CLASSIFY_MAX_OUTPUT)
    ok = run("summarize", prompts.SUMMARIZE_SYSTEM, prompts.SUMMARIZE_SCHEMA, settings.SUMMARIZE_MAX_CONTENT_CHARS, SUMMARIZE_MAX_OUTPUT) and ok
    if settings.LLM_PROVIDER == "groq":
        for model in sorted({settings.CLASSIFY_MODEL, settings.SUMMARIZE_MODEL}):
            print(f"Token đã dùng hôm nay (UTC) — {model}: {budget.used_today(model)}/{settings.GROQ_DAILY_TOKEN_CAP}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
