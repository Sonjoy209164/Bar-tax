import logging
import math
from functools import lru_cache
from typing import Any

from app.core.schemas import QuerySignals, RetrievalHit
from app.core.settings import get_settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import availability depends on runtime extras
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
except Exception:  # pragma: no cover - exercised through graceful fallback
    torch = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


@lru_cache(maxsize=2)
def _load_reranker_bundle(model_name: str) -> tuple[Any, Any, str]:
    if torch is None or AutoTokenizer is None or AutoModelForSequenceClassification is None:
        raise RuntimeError("Transformers reranker dependencies are not installed.")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()
    return tokenizer, model, device


def _score_pairs_with_transformers(
    query_text: str,
    passages: list[str],
    *,
    model_name: str,
    batch_size: int = 8,
    max_length: int = 512,
) -> list[float]:
    tokenizer, model, device = _load_reranker_bundle(model_name)
    pairs = [[query_text, passage] for passage in passages]
    all_scores: list[float] = []
    for start in range(0, len(pairs), batch_size):
        batch_pairs = pairs[start : start + batch_size]
        with torch.inference_mode():
            inputs = tokenizer(
                batch_pairs,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            inputs = {key: value.to(device) for key, value in inputs.items()}
            logits = model(**inputs, return_dict=True).logits.view(-1).float().cpu().tolist()
        all_scores.extend(_sigmoid(score) for score in logits)
    return all_scores


def rerank_retrieval_hits(
    *,
    query_text: str,
    analyzed_query: QuerySignals,
    hits: list[RetrievalHit],
    top_n: int = 20,
) -> list[RetrievalHit]:
    if not hits:
        return hits

    settings = get_settings()
    provider = settings.reranker_provider.lower()
    if provider in {"", "none", "mock"}:
        return hits
    if provider != "transformers":
        logger.warning("Unsupported reranker provider; skipping model reranking.", extra={"provider": provider})
        return hits

    effective_query = analyzed_query.rewritten_query or analyzed_query.normalized_query or query_text
    candidates = [hit.model_copy(deep=True) for hit in hits[:top_n]]
    trailing_hits = [hit.model_copy(deep=True) for hit in hits[top_n:]]
    passages = [
        "\n".join(part for part in [" > ".join(hit.heading_path), hit.normalized_text] if part).strip()
        for hit in candidates
    ]
    try:
        reranker_scores = _score_pairs_with_transformers(
            effective_query,
            passages,
            model_name=settings.reranker_model_name,
        )
    except Exception as exc:  # pragma: no cover - exercised by runtime fallback
        logger.warning(
            "Model reranker unavailable; continuing with heuristic ranking.",
            extra={"provider": provider, "model_name": settings.reranker_model_name, "error": str(exc)},
        )
        return hits

    for hit, reranker_score in zip(candidates, reranker_scores, strict=False):
        hit.intermediate_scores["model_reranker_score"] = round(reranker_score, 6)
        hit.score = round(hit.score + (reranker_score * 4.0), 6)

    candidates.sort(key=lambda hit: hit.score, reverse=True)
    return candidates + trailing_hits
