"""Local, free multilingual sentence embeddings used for cross-source
duplicate/topic clustering via pgvector. No API key needed; the model is
downloaded once from Hugging Face on first use and cached locally.
"""

from functools import lru_cache

from app.config import settings


@lru_cache
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.EMBEDDING_MODEL_NAME)


def embed_text(text: str) -> list[float]:
    model = _get_model()
    vector = model.encode(text[:2000], normalize_embeddings=True)
    return vector.tolist()
