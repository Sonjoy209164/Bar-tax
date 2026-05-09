from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_model = None
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _load_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Loaded multilingual embedding model: %s", _MODEL_NAME)
    except ImportError:
        logger.warning(
            "sentence-transformers not installed. "
            "Run: pip install sentence-transformers  "
            "Falling back to deterministic embeddings."
        )
        _model = None
    except Exception as exc:
        logger.warning("Failed to load multilingual model: %s", exc)
        _model = None
    return _model


def embed_text(text: str) -> list[float] | None:
    """Embed a single text. Returns None if sentence-transformers unavailable."""
    model = _load_model()
    if model is None:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return None


def embed_batch(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch. Returns None if unavailable."""
    model = _load_model()
    if model is None:
        return None
    try:
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        return [v.tolist() for v in vecs]
    except Exception as exc:
        logger.warning("Batch embedding failed: %s", exc)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity (no numpy required for single-pair)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_search(
    query: str,
    documents: list[dict[str, Any]],   # each must have "text" and "id" keys
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Score documents against query by cosine similarity.
    If model unavailable, falls back to BM25-style token overlap scoring.
    """
    query_vec = embed_text(query)
    if query_vec is None:
        return _bm25_fallback(query, documents, top_k)

    doc_texts = [d["text"] for d in documents]
    doc_vecs = embed_batch(doc_texts)
    if doc_vecs is None:
        return _bm25_fallback(query, documents, top_k)

    scored = []
    for doc, vec in zip(documents, doc_vecs):
        score = cosine_similarity(query_vec, vec)
        scored.append({**doc, "score": round(score, 4)})

    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def _bm25_fallback(query: str, documents: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    query_tokens = set(query.casefold().split())
    scored = []
    for doc in documents:
        doc_tokens = set(doc["text"].casefold().split())
        overlap = len(query_tokens & doc_tokens)
        scored.append({**doc, "score": overlap / max(len(query_tokens), 1)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def is_available() -> bool:
    return _load_model() is not None
