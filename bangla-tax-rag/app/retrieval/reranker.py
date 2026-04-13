import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

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


def _resolve_local_hf_snapshot(model_name: str) -> str | None:
    cache_root = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))
    model_cache_dir = cache_root / f"models--{model_name.replace('/', '--')}"
    snapshots_dir = model_cache_dir / "snapshots"
    if not snapshots_dir.exists():
        return None
    candidate_snapshots = sorted(path for path in snapshots_dir.iterdir() if path.is_dir())
    if not candidate_snapshots:
        return None
    required_files = ("config.json",)
    model_files = ("model.safetensors", "pytorch_model.bin")
    for snapshot_path in reversed(candidate_snapshots):
        if all((snapshot_path / filename).exists() for filename in required_files) and any(
            (snapshot_path / filename).exists() for filename in model_files
        ):
            return str(snapshot_path)
    return None


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


@lru_cache(maxsize=2)
def _load_reranker_bundle(model_name: str) -> tuple[Any, Any, str]:
    if torch is None or AutoTokenizer is None or AutoModelForSequenceClassification is None:
        raise RuntimeError("Transformers reranker dependencies are not installed.")

    local_model_path = _resolve_local_hf_snapshot(model_name)
    try:
        load_target = local_model_path or model_name
        tokenizer = AutoTokenizer.from_pretrained(load_target, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(load_target, local_files_only=True)
    except Exception:
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


def _score_pairs_with_embedding_fallback(
    query_text: str,
    passages: list[str],
    *,
    model_name: str,
) -> list[float]:
    from app.retrieval.dense import _encode_texts_with_transformers

    query_embedding = _encode_texts_with_transformers([query_text], model_name=model_name)[0]
    passage_embeddings = _encode_texts_with_transformers(passages, model_name=model_name)
    similarities = np.asarray(passage_embeddings @ query_embedding, dtype=np.float32)
    return similarities.tolist()


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
        reranker_backend = "cross_encoder"
    except Exception as exc:  # pragma: no cover - exercised by runtime fallback
        logger.warning(
            "Cross-encoder reranker unavailable; falling back to embedding-based reranking.",
            extra={"provider": provider, "model_name": settings.reranker_model_name, "error": str(exc)},
        )
        try:
            reranker_scores = _score_pairs_with_embedding_fallback(
                effective_query,
                passages,
                model_name=settings.embedding_model_name,
            )
            reranker_backend = "embedding_fallback"
        except Exception as fallback_exc:  # pragma: no cover - runtime safety
            logger.warning(
                "Embedding fallback reranker unavailable; continuing with heuristic ranking.",
                extra={
                    "provider": provider,
                    "reranker_model_name": settings.reranker_model_name,
                    "embedding_model_name": settings.embedding_model_name,
                    "error": str(fallback_exc),
                },
            )
            return hits

    for hit, reranker_score in zip(candidates, reranker_scores, strict=False):
        hit.intermediate_scores["model_reranker_score"] = round(reranker_score, 6)
        hit.intermediate_scores["model_reranker_backend"] = reranker_backend
        hit.score = round(hit.score + (reranker_score * 4.0), 6)

    candidates.sort(key=lambda hit: hit.score, reverse=True)
    return candidates + trailing_hits
