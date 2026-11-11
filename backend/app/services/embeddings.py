"""Local, free multilingual sentence embeddings used for cross-source
duplicate/topic clustering via pgvector. No API key needed; the model is
downloaded once from Hugging Face on first use and cached locally.
"""

import threading
from functools import lru_cache

from app.config import settings

# SentenceTransformer.encode isn't guaranteed thread-safe; the API serves
# requests from a thread pool.
_encode_lock = threading.Lock()


@lru_cache
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.EMBEDDING_MODEL_NAME)


def embed_text(text: str) -> list[float]:
    model = _get_model()
    with _encode_lock:
        vector = model.encode(text[:2000], normalize_embeddings=True)
    return vector.tolist()


def warm_up() -> None:
    """Loads the model ahead of the first request (call from a thread)."""
    embed_text("warm up")
