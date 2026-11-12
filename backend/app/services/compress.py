"""Local (CPU-only, no tokens) shrinking of article text before it is sent
to an LLM.

1. clean(): drop lines that carry no information for a summary — URLs,
   "read more"/related-article lines, photo credits, social calls to action,
   hashtag-only lines, YouTube chapter timestamps and sponsor blurbs.
2. condense(): news is written as an inverted pyramid, so keep the lead
   (first sentences) and then the remaining sentences that share the most
   words with the title, in original order, up to a character budget.

Typical effect: ~3,700 → ≤2,400 characters per article (~35% fewer prompt
tokens on the summarize call) while keeping the facts a 3-bullet summary
needs.
"""

import re

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_TIMESTAMP_LINE_RE = re.compile(r"^\s*\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*[-–—:]?\s*")
_HASHTAGS_ONLY_RE = re.compile(r"^(?:\s*#[\w\-]+)+\s*$", re.UNICODE)
_NOISE_LINE_RE = re.compile(
    r"^\s*(xem thêm|đọc thêm|tin liên quan|bài liên quan|ảnh\s*:|ảnh minh họa|nguồn\s*:|video\s*:|"
    r"theo dõi|đăng ký|subscribe|follow|like|share|related|read more|see also|photo:|image:|credit:|"
    r"advertisement|quảng cáo|tài trợ|sponsored|liên hệ|hotline|mua ngay|shop|link mua|"
    r"facebook|tiktok|instagram|zalo|telegram|discord)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[\"“'(\[]?[A-ZÀ-Ỹ0-9])")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_STOPWORDS = {
    # Vietnamese
    "và", "của", "là", "có", "cho", "các", "những", "một", "được", "trong", "với", "này", "đã", "khi", "từ",
    "theo", "về", "để", "như", "người", "không", "sẽ", "cũng", "đến", "năm", "tại", "vào", "ra", "lên",
    # English
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "was", "were", "be",
    "it", "its", "that", "this", "as", "at", "by", "from", "has", "have", "will", "about", "after",
}


def clean(text: str) -> str:
    kept: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = _URL_RE.sub("", raw).strip()
        if not line:
            continue
        if _HASHTAGS_ONLY_RE.match(line) or _NOISE_LINE_RE.match(line):
            continue
        if _TIMESTAMP_LINE_RE.match(raw) and len(line) < 120:
            continue  # YouTube chapter list
        key = line.lower()
        if key in seen:  # repeated boilerplate
            continue
        seen.add(key)
        if len(line) < 25 and not line.endswith((".", "!", "?", ":")):
            continue  # captions, button labels, bylines
        kept.append(line)
    return "\n".join(kept)


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) > 1 and w not in _STOPWORDS}


def condense(title: str, text: str, max_chars: int, lead_chars: int = 900) -> str:
    """Lead + title-relevant sentences, original order, ≤ max_chars."""
    text = clean(text)
    if len(text) <= max_chars:
        return text
    sentences = [s.strip() for p in text.split("\n") for s in _SENTENCE_SPLIT_RE.split(p) if s.strip()]
    if not sentences:
        return text[:max_chars]

    chosen: set[int] = set()
    used = 0
    for i, sentence in enumerate(sentences):  # the lead
        if used >= lead_chars:
            break
        chosen.add(i)
        used += len(sentence) + 1

    title_words = _words(title)
    ranked = sorted(
        (i for i in range(len(sentences)) if i not in chosen),
        key=lambda i: (-len(_words(sentences[i]) & title_words), -len(_words(sentences[i])), i),
    )
    for i in ranked:
        if used + len(sentences[i]) + 1 > max_chars:
            continue
        chosen.add(i)
        used += len(sentences[i]) + 1

    return " ".join(sentences[i] for i in sorted(chosen))[:max_chars]
