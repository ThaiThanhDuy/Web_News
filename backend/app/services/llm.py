"""LLM wrapper: turns raw article text into structured JSON (summary
bullets, one-line takeaway, keywords, category, sentiment, AI hotness
score). Runs entirely locally through Ollama — see start-ollama.sh and
OLLAMA_BASE_URL / OLLAMA_MODEL in app/config.py.
"""

import json
import logging

import requests

from app.config import settings
from app.constants import CATEGORIES

logger = logging.getLogger(__name__)


class TransientLLMError(Exception):
    """Raised for retryable errors (local Ollama server not reachable / not
    warmed up yet / 5xx). Callers should back off and retry rather than
    giving up on the article."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after

_CATEGORY_SLUGS = [c["slug"] for c in CATEGORIES]

# Precise per-category rules with counter-examples. Small/fast models
# default to whichever category feels "safest" without this — in practice
# almost everything not obviously mobile/AI/game ended up in phan-mem
# (business, policy, deals, leadership news, entertainment...).
CATEGORY_GUIDE = """Định nghĩa từng chuyên mục — chọn ĐÚNG MỘT giá trị category, dựa sát vào định nghĩa:
- ai: Tin về trí tuệ nhân tạo — mô hình AI, chatbot, công cụ AI tạo sinh, công ty AI (OpenAI, Anthropic, Google DeepMind...). Kể cả tin kinh doanh/nhân sự CỦA một công ty AI (vd. "Giám đốc OpenAI từ chức") vẫn thuộc "ai", không thuộc "phan-mem".
- di-dong: Điện thoại, tablet, thiết bị đeo (đồng hồ, tai nghe), hệ điều hành di động (Android/iOS), mạng di động, ứng dụng/tính năng gắn liền với điện thoại.
- may-tinh: CHỈ dùng khi bài viết nói cụ thể về một máy tính để bàn (PC) hoặc laptop, hoặc linh kiện lắp ráp PC gắn với sản phẩm/thương hiệu cụ thể (CPU, GPU/card đồ họa, RAM, mainboard, ổ cứng, tản nhiệt, màn hình, bàn phím, chuột máy tính, thương hiệu như Dell, HP, Asus, Lenovo, Apple MacBook...). KHÔNG dùng cho điện thoại/tablet/đồng hồ/tai nghe dù bài nói về sự kiện ra mắt nhiều sản phẩm công nghệ cùng lúc (vd. "Made by Google ra mắt Pixel 11, Pixel Watch" → "di-dong", không phải "may-tinh" chỉ vì đó là sự kiện công nghệ). KHÔNG dùng cho robot (kể cả "robot phone") → "phan-cung" hoặc "di-dong" tùy sản phẩm. KHÔNG dùng cho thiết bị gia dụng, rạp hát gia đình, máy cắt cỏ, hay bất kỳ thiết bị nào không phải PC/laptop — những tin đó thuộc "khac" hoặc chuyên mục khác phù hợp hơn, không phải "may-tinh".
- phan-cung: Phần cứng và thiết bị điện tử KHÁC — không phải điện thoại/tablet (→ di-dong), không phải PC/laptop/linh kiện PC (→ may-tinh). Gồm: ngành công nghiệp bán dẫn/chip nói chung (sản xuất, nhà máy, công nghệ chip không gắn với một sản phẩm PC cụ thể), máy in, robot vật lý, drone, camera, thiết bị IoT/nhà thông minh, thiết bị đeo không phải điện thoại.
- phan-mem: CHỈ dùng khi bài viết nói cụ thể về một phần mềm/ứng dụng máy tính/hệ điều hành desktop/dịch vụ web cụ thể (vd. Windows, Google Maps, một app SaaS). KHÔNG dùng cho tin kinh doanh chung, chính sách, nhân sự lãnh đạo, khuyến mãi/giá bán, hay bất kỳ nội dung nào không thực sự nói về một phần mềm cụ thể.
- game: Trò chơi điện tử, ngành công nghiệp game, esports, thiết bị chơi game.
- startup: Gọi vốn, khởi nghiệp công nghệ, thương vụ đầu tư mạo hiểm, quỹ đầu tư công nghệ.
- mang-xa-hoi: Nền tảng mạng xã hội cụ thể (Facebook, TikTok, X, Instagram...) và các tính năng/chính sách của chúng.
- an-ninh-mang: Bảo mật, lỗ hổng phần mềm, tấn công mạng, rò rỉ/đánh cắp dữ liệu, quyền riêng tư, lừa đảo trực tuyến.
- khoa-hoc: Khoa học, không gian/vũ trụ, nghiên cứu học thuật, giao thông công nghệ cao (tàu đệm từ, xe điện, hàng không), y sinh công nghệ, năng lượng.
- khac: BẮT BUỘC dùng cho những tin KHÔNG mô tả trực tiếp một sản phẩm/công nghệ cụ thể thuộc các nhóm trên — ví dụ: tin kinh doanh/tài chính/chính sách/pháp lý chung của ngành công nghệ, tin nhân sự lãnh đạo (trừ công ty AI), khuyến mãi/giảm giá/mua sắm, giải trí/streaming không phải mạng xã hội, sự kiện/hội nghị nói chung. Khi phân vân giữa "khac" và một chuyên mục khác, hãy ưu tiên chọn "khac"."""

SYSTEM_PROMPT = f"""Bạn là một biên tập viên tin tức công nghệ chuyên nghiệp tại Việt Nam.
Đọc tiêu đề và nội dung bài báo được cung cấp, sau đó trả về DUY NHẤT một đối tượng JSON hợp lệ
(không kèm giải thích, không dùng markdown code fence) theo đúng schema sau:

{{
  "summary_bullets": ["<ý chính 1>", "<ý chính 2>", "<ý chính 3>"],
  "one_line_takeaway": "<câu tóm tắt nhanh nhất, tối đa 25 từ, tiếng Việt>",
  "keywords": ["<từ khóa 1>", "<từ khóa 2>", "<từ khóa 3>", "<từ khóa 4>", "<từ khóa 5>"],
  "category": "<một trong: {', '.join(_CATEGORY_SLUGS)}>",
  "sentiment": "<một trong: positive, neutral, negative>",
  "ai_hotness_score": <số nguyên từ 0 đến 100, thể hiện mức độ đáng chú ý / quan trọng của tin với độc giả công nghệ Việt Nam>
}}

{CATEGORY_GUIDE}

Chỉ trả về JSON, không thêm bất kỳ văn bản nào khác."""

CLASSIFY_SYSTEM_PROMPT = f"""Bạn là một biên tập viên tin tức công nghệ chuyên nghiệp tại Việt Nam.
Đọc tiêu đề và nội dung bài báo, sau đó trả về DUY NHẤT một đối tượng JSON hợp lệ (không giải thích,
không markdown) theo schema: {{"category": "<một trong: {', '.join(_CATEGORY_SLUGS)}>"}}

{CATEGORY_GUIDE}

Chỉ trả về JSON, không thêm bất kỳ văn bản nào khác."""


class ArticleAnalysis(dict):
    """Thin typed-ish wrapper; behaves like a dict with validated keys."""


def _chat_json(system_prompt: str, title: str, content: str) -> dict | None:
    user_prompt = f"Tiêu đề: {title}\n\nNội dung:\n{content[:6000]}"

    try:
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.3},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            # Local CPU inference for the full analysis prompt can take
            # several minutes on a larger model (qwen2.5:14b-instruct here) —
            # give it plenty of room before giving up. This was measured too
            # tight at 300s for the smaller 7b model under load already, so
            # 14b needs more headroom, not less.
            timeout=900,
        )
        response.raise_for_status()
    except (requests.ConnectionError, requests.Timeout) as exc:
        logger.warning("Ollama unreachable/slow for article %r: %s", title, exc)
        raise TransientLLMError(str(exc), retry_after=30) from exc
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status is not None and status >= 500:
            raise TransientLLMError(str(exc), retry_after=30) from exc
        logger.exception("Ollama call failed for article: %s", title)
        return None
    except Exception:
        logger.exception("Ollama call failed for article: %s", title)
        return None

    try:
        return json.loads(response.json()["message"]["content"])
    except (json.JSONDecodeError, TypeError, KeyError):
        logger.warning("Non-JSON Ollama response for article: %s", title)
        return None


def analyze_article(title: str, content: str) -> ArticleAnalysis | None:
    """Returns the parsed analysis, or None if the article can never be
    analyzed (malformed model output). Raises TransientLLMError when Ollama
    is unreachable/overloaded — callers should retry those."""
    data = _chat_json(SYSTEM_PROMPT, title, content)
    return _validate(data) if data is not None else None


def classify_category(title: str, content: str) -> str | None:
    """Cheaper, category-only call — used to reclassify already-processed
    articles without redoing the full summary/keywords/sentiment analysis."""
    data = _chat_json(CLASSIFY_SYSTEM_PROMPT, title, content)
    if data is None:
        return None
    category = str(data.get("category", "")).strip().lower()
    return category if category in _CATEGORY_SLUGS else None


def _validate(data: dict) -> ArticleAnalysis | None:
    try:
        bullets = [str(b).strip() for b in data["summary_bullets"]][:3]
        takeaway = str(data["one_line_takeaway"]).strip()
        keywords = [str(k).strip() for k in data["keywords"]][:5]
        category = str(data.get("category", "khac")).strip().lower()
        if category not in _CATEGORY_SLUGS:
            category = "khac"
        sentiment = str(data.get("sentiment", "neutral")).strip().lower()
        if sentiment not in {"positive", "neutral", "negative"}:
            sentiment = "neutral"
        hotness = float(data.get("ai_hotness_score", 50))
        hotness = max(0.0, min(100.0, hotness))
    except (KeyError, TypeError, ValueError):
        logger.warning("Malformed LLM JSON response: %s", data)
        return None

    if not bullets or not takeaway:
        return None

    return ArticleAnalysis(
        summary_bullets=bullets,
        one_line_takeaway=takeaway,
        keywords=keywords,
        category=category,
        sentiment=sentiment,
        ai_hotness_score=hotness,
    )
