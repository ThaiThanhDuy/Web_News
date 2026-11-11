"""Deterministic text helpers used before any AI call: URL canonicalization,
cleaning + personal-data redaction, exact (SHA-256) and near-duplicate
(SimHash) fingerprints, and a cheap language guess."""

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# ------------------------------------------------------------------- URLs

_TRACKING_PARAMS = re.compile(
    r"^(utm_\w+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|igshid|ref|ref_src|cmpid|guccounter|"
    r"guce_referrer|guce_referrer_sig|ncid|sr_share|taid)$",
    re.IGNORECASE,
)


def canonical_url(url: str) -> str:
    """Stable dedupe key for a link: lowercase scheme/host, no fragment,
    no tracking parameters, no default port, no trailing slash."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if parts.port and not ((scheme == "http" and parts.port == 80) or (scheme == "https" and parts.port == 443)):
        host = f"{host}:{parts.port}"
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_PARAMS.match(k))
    )
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, query, ""))


def domain_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


# ---------------------------------------------------- cleaning + redaction

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Vietnamese mobile/landline numbers (0xx / +84 / 84 prefixes, with optional
# separators) plus generic international numbers of 9+ digits.
_PHONE_RE = re.compile(
    r"(?<![\w/.-])(?:\+?84|0)(?:[\s.-]?\d){8,10}(?![\w/-])"
    r"|(?<![\w/.-])\+\d{1,3}(?:[\s.-]?\d){8,12}(?![\w/-])"
)


def redact_personal_data(value: str) -> str:
    """Removes e-mail addresses and phone numbers. Runs before anything is
    stored (raw files, DB) or sent to an AI provider."""
    value = _EMAIL_RE.sub("[email]", value)
    return _PHONE_RE.sub("[sđt]", value)


def clean_text(value: str | None) -> str:
    """HTML/whitespace normalization + personal-data redaction."""
    if not value:
        return ""
    value = html.unescape(_TAG_RE.sub(" ", value))
    value = unicodedata.normalize("NFC", value)
    lines = [_WS_RE.sub(" ", line).strip() for line in value.splitlines()]
    value = _MULTI_NL_RE.sub("\n\n", "\n".join(lines)).strip()
    return redact_personal_data(value)


# --------------------------------------------------------- fingerprints

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(value: str) -> list[str]:
    return _WORD_RE.findall(unicodedata.normalize("NFC", value).lower())


def content_hash(title: str, content: str) -> str:
    """SHA-256 of the normalized text: identical text => identical hash,
    regardless of whitespace, case, or markup differences."""
    normalized = " ".join(_tokens(f"{title}\n{content}"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def simhash64(value: str, shingle: int = 3) -> int:
    """64-bit SimHash over word shingles, returned as a *signed* 64-bit int
    so it fits a Postgres BIGINT. Near-identical texts differ in few bits."""
    tokens = _tokens(value)
    if len(tokens) < shingle:
        grams = [" ".join(tokens)] if tokens else [""]
    else:
        grams = [" ".join(tokens[i : i + shingle]) for i in range(len(tokens) - shingle + 1)]
    weights = [0] * 64
    for gram in grams:
        h = int.from_bytes(hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            weights[bit] += 1 if h >> bit & 1 else -1
    value_u = sum(1 << bit for bit in range(64) if weights[bit] > 0)
    return value_u - (1 << 64) if value_u >= 1 << 63 else value_u


def hamming64(a: int, b: int) -> int:
    return ((a ^ b) & 0xFFFFFFFFFFFFFFFF).bit_count()


# -------------------------------------------------------------- language

# Letters that only occur in Vietnamese among common Latin-script languages.
_VI_CHARS = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")


def detect_language(value: str) -> str:
    letters = [c for c in value.lower() if c.isalpha()]
    if not letters:
        return "und"
    vi = sum(1 for c in letters if c in _VI_CHARS)
    if vi / len(letters) > 0.02:
        return "vi"
    ascii_letters = sum(1 for c in letters if c.isascii())
    return "en" if ascii_letters / len(letters) > 0.95 else "other"


# ---------------------------------------------------------------- search


def fold(value: str | None) -> str:
    """Lowercase, accent-free form for search: "Điện thoại" -> "dien thoai",
    so queries match with or without Vietnamese diacritics."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", value.lower().replace("đ", "d").replace("Đ", "d"))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.split())


def fold_tag(value: str | None) -> str:
    """Hashtag form: folded with spaces removed ("iPhone 18" -> "iphone18")."""
    return fold(value).replace(" ", "")
