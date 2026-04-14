import logging
import math
import os
from abc import ABC, abstractmethod
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from pydantic import BaseModel, Field, field_validator

from app.core.utils import normalize_text, tokenize_for_bm25

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

DEFAULT_COHERE_BASE_URL = "https://api.cohere.com/v2"


class RerankerProvider(StrEnum):
    NONE = "none"
    COHERE = "cohere"
    TRANSFORMERS = "transformers"
    DETERMINISTIC = "deterministic"


class RerankerConfig(BaseModel):
    provider: RerankerProvider = RerankerProvider.TRANSFORMERS
    model_name: str = "rerank-v3.5"
    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_documents: int = Field(default=20, ge=1, le=200)
    batch_size: int = Field(default=8, ge=1, le=64)
    max_length: int = Field(default=512, ge=32, le=4096)

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.rstrip("/")
        return stripped or None


class RerankerDocument(BaseModel):
    document_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Reranker documents must contain non-empty text")
        return stripped


class RerankedDocument(BaseModel):
    document_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float
    rank: int


class RerankResult(BaseModel):
    provider: RerankerProvider
    model_name: str
    top_k: int
    backend: str
    results: list[RerankedDocument] = Field(default_factory=list)


class DocumentReranker(ABC):
    def __init__(self, config: RerankerConfig) -> None:
        self.config = config

    @property
    def provider(self) -> RerankerProvider:
        return self.config.provider

    @abstractmethod
    def rerank(
        self,
        query_text: str,
        documents: list[RerankerDocument],
        *,
        top_k: int | None = None,
    ) -> RerankResult:
        raise NotImplementedError


class DeterministicDocumentReranker(DocumentReranker):
    def rerank(
        self,
        query_text: str,
        documents: list[RerankerDocument],
        *,
        top_k: int | None = None,
    ) -> RerankResult:
        query_terms = set(tokenize_for_bm25(normalize_text(query_text)))
        scored: list[tuple[RerankerDocument, float]] = []
        for document in documents:
            doc_terms = set(tokenize_for_bm25(normalize_text(document.text)))
            overlap = len(query_terms & doc_terms)
            normalization = max(len(query_terms), 1)
            score = overlap / normalization
            if document.metadata.get("section_number") and document.metadata.get("section_number") in query_terms:
                score += 0.2
            if document.metadata.get("chunk_type") in {"table", "definition"}:
                score += 0.05
            scored.append((document, score))
        return _build_rerank_result(
            provider=self.provider,
            model_name=self.config.model_name,
            backend="deterministic_overlap",
            scored_documents=scored,
            top_k=top_k or min(len(documents), self.config.max_documents),
        )


class TransformersDocumentReranker(DocumentReranker):
    def rerank(
        self,
        query_text: str,
        documents: list[RerankerDocument],
        *,
        top_k: int | None = None,
    ) -> RerankResult:
        candidate_documents = documents[: self.config.max_documents]
        scores = _score_pairs_with_transformers(
            query_text,
            [document.text for document in candidate_documents],
            model_name=self.config.model_name,
            batch_size=self.config.batch_size,
            max_length=self.config.max_length,
        )
        return _build_rerank_result(
            provider=self.provider,
            model_name=self.config.model_name,
            backend="cross_encoder",
            scored_documents=list(zip(candidate_documents, scores, strict=True)),
            top_k=top_k or len(candidate_documents),
        )


class CohereDocumentReranker(DocumentReranker):
    def rerank(
        self,
        query_text: str,
        documents: list[RerankerDocument],
        *,
        top_k: int | None = None,
    ) -> RerankResult:
        if not self.config.api_key:
            raise ValueError("Cohere reranker requires an API key")
        candidate_documents = documents[: self.config.max_documents]
        effective_top_k = min(top_k or len(candidate_documents), len(candidate_documents))
        payload = {
            "model": self.config.model_name,
            "query": query_text,
            "documents": [document.text for document in candidate_documents],
            "top_n": effective_top_k,
        }
        base_url = self.config.base_url or DEFAULT_COHERE_BASE_URL
        with httpx.Client(timeout=self.config.timeout_seconds) as client:
            response = client.post(
                f"{base_url}/rerank",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            response_payload = response.json()

        scored: list[tuple[RerankerDocument, float]] = []
        for rank_position, item in enumerate(response_payload.get("results", []), start=1):
            index = item["index"]
            scored.append((candidate_documents[index], float(item["relevance_score"])))
        return _build_rerank_result(
            provider=self.provider,
            model_name=self.config.model_name,
            backend="cohere_api",
            scored_documents=scored,
            top_k=effective_top_k,
        )


def build_reranker(config: RerankerConfig | None = None) -> DocumentReranker | None:
    resolved_config = config or reranker_config_from_settings()
    if resolved_config.provider is RerankerProvider.NONE:
        return None
    if resolved_config.provider is RerankerProvider.DETERMINISTIC:
        return DeterministicDocumentReranker(resolved_config)
    if resolved_config.provider is RerankerProvider.TRANSFORMERS:
        return TransformersDocumentReranker(resolved_config)
    if resolved_config.provider is RerankerProvider.COHERE:
        return CohereDocumentReranker(resolved_config)
    raise ValueError(f"Unsupported reranker provider: {resolved_config.provider}")


def reranker_config_from_settings() -> RerankerConfig:
    settings = get_settings()
    provider_value = settings.reranker_provider.strip().lower()
    return RerankerConfig(
        provider=RerankerProvider(provider_value),
        model_name=settings.reranker_model_name,
        base_url=getattr(settings, "reranker_base_url", None),
        api_key=getattr(settings, "reranker_api_key", None),
    )


def _build_rerank_result(
    *,
    provider: RerankerProvider,
    model_name: str,
    backend: str,
    scored_documents: list[tuple[RerankerDocument, float]],
    top_k: int,
) -> RerankResult:
    ranked = sorted(scored_documents, key=lambda item: item[1], reverse=True)[:top_k]
    results = [
        RerankedDocument(
            document_id=document.document_id,
            text=document.text,
            metadata=document.metadata,
            relevance_score=float(score),
            rank=rank,
        )
        for rank, (document, score) in enumerate(ranked, start=1)
    ]
    return RerankResult(
        provider=provider,
        model_name=model_name,
        top_k=top_k,
        backend=backend,
        results=results,
    )

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
