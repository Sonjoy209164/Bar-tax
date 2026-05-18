from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

import httpx
import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.settings import get_settings
from app.retrieval.dense import _encode_texts_with_transformers

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class EmbeddingProvider(StrEnum):
    OPENAI = "openai"
    TRANSFORMERS = "transformers"
    DETERMINISTIC = "deterministic"
    MULTILINGUAL = "multilingual"


class EmbedderConfig(BaseModel):
    provider: EmbeddingProvider = EmbeddingProvider.OPENAI
    model_name: str = "text-embedding-3-large"
    base_url: str | None = None
    api_key: str | None = None
    dimensions: int | None = Field(default=None, ge=1)
    timeout_seconds: float = Field(default=30.0, gt=0)
    normalize: bool = True

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.rstrip("/")
        return cleaned or None


class EmbeddingBatch(BaseModel):
    vectors: list[list[float]] = Field(default_factory=list)
    model_name: str
    provider: EmbeddingProvider
    dimensions: int

    @model_validator(mode="after")
    def validate_dimensions(self) -> "EmbeddingBatch":
        for vector in self.vectors:
            if len(vector) != self.dimensions:
                raise ValueError("Embedding vector length does not match dimensions")
        return self


class TextEmbedder(ABC):
    def __init__(self, config: EmbedderConfig) -> None:
        self.config = config

    @property
    def provider(self) -> EmbeddingProvider:
        return self.config.provider

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> EmbeddingBatch:
        raise NotImplementedError

    def embed_text(self, text: str) -> list[float]:
        batch = self.embed_texts([text])
        return batch.vectors[0]


class OpenAITextEmbedder(TextEmbedder):
    def embed_texts(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            dimensions = self.config.dimensions or 0
            return EmbeddingBatch(vectors=[], model_name=self.config.model_name, provider=self.provider, dimensions=dimensions)
        if not self.config.api_key:
            raise ValueError("OpenAI embedding provider requires an API key")

        payload: dict[str, Any] = {
            "input": texts,
            "model": self.config.model_name,
        }
        if self.config.dimensions:
            payload["dimensions"] = self.config.dimensions

        base_url = self.config.base_url or DEFAULT_OPENAI_BASE_URL
        with httpx.Client(timeout=self.config.timeout_seconds) as client:
            response = client.post(
                f"{base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            response_payload = response.json()

        vectors = [item["embedding"] for item in response_payload.get("data", [])]
        if len(vectors) != len(texts):
            raise ValueError("Embedding response length did not match input length")
        dimensions = len(vectors[0]) if vectors else (self.config.dimensions or 0)
        return EmbeddingBatch(
            vectors=[_normalize_vector(vector) if self.config.normalize else vector for vector in vectors],
            model_name=response_payload.get("model", self.config.model_name),
            provider=self.provider,
            dimensions=dimensions,
        )


class TransformersTextEmbedder(TextEmbedder):
    def embed_texts(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(vectors=[], model_name=self.config.model_name, provider=self.provider, dimensions=0)
        embeddings = _encode_texts_with_transformers(texts, model_name=self.config.model_name)
        if self.config.dimensions:
            embeddings = _truncate_embeddings(embeddings, self.config.dimensions)
        if self.config.normalize:
            embeddings = _normalize_matrix(embeddings)
        vectors = embeddings.astype("float32").tolist()
        dimensions = int(embeddings.shape[1]) if embeddings.size else 0
        return EmbeddingBatch(
            vectors=vectors,
            model_name=self.config.model_name,
            provider=self.provider,
            dimensions=dimensions,
        )


class DeterministicTextEmbedder(TextEmbedder):
    def embed_texts(self, texts: list[str]) -> EmbeddingBatch:
        dimensions = self.config.dimensions or 256
        matrix = np.vstack([_hash_embedding(text, dimensions) for text in texts]) if texts else np.zeros((0, dimensions), dtype=np.float32)
        if self.config.normalize and matrix.size:
            matrix = _normalize_matrix(matrix)
        return EmbeddingBatch(
            vectors=matrix.astype("float32").tolist(),
            model_name=self.config.model_name,
            provider=self.provider,
            dimensions=dimensions,
        )


class MultilingualTextEmbedder(TextEmbedder):
    """Wraps paraphrase-multilingual-MiniLM-L12-v2 via sentence-transformers.
    Falls back to deterministic hashing if sentence-transformers is unavailable.
    """

    def embed_texts(self, texts: list[str]) -> EmbeddingBatch:
        from app.retrieval.multilingual_provider import embed_batch, is_available
        if not texts:
            return EmbeddingBatch(vectors=[], model_name=self.config.model_name, provider=self.provider, dimensions=0)
        if is_available():
            vecs = embed_batch(texts)
            if vecs:
                dimensions = len(vecs[0])
                return EmbeddingBatch(
                    vectors=vecs,
                    model_name=self.config.model_name or "paraphrase-multilingual-MiniLM-L12-v2",
                    provider=self.provider,
                    dimensions=dimensions,
                )
        # Graceful fallback to deterministic
        fallback = DeterministicTextEmbedder(self.config)
        return fallback.embed_texts(texts)


def build_embedder(config: EmbedderConfig | None = None) -> TextEmbedder:
    resolved_config = config or embedder_config_from_settings()
    if resolved_config.provider is EmbeddingProvider.OPENAI:
        return OpenAITextEmbedder(resolved_config)
    if resolved_config.provider is EmbeddingProvider.TRANSFORMERS:
        return TransformersTextEmbedder(resolved_config)
    if resolved_config.provider is EmbeddingProvider.DETERMINISTIC:
        return DeterministicTextEmbedder(resolved_config)
    if resolved_config.provider is EmbeddingProvider.MULTILINGUAL:
        return MultilingualTextEmbedder(resolved_config)
    raise ValueError(f"Unsupported embedding provider: {resolved_config.provider}")


def embed_texts(texts: list[str], config: EmbedderConfig | None = None) -> EmbeddingBatch:
    return build_embedder(config).embed_texts(texts)


def embed_query(text: str, config: EmbedderConfig | None = None) -> list[float]:
    return build_embedder(config).embed_text(text)


def embedder_config_from_settings() -> EmbedderConfig:
    settings = get_settings()
    provider_value = settings.embedding_provider.strip().lower()
    provider = EmbeddingProvider(provider_value)
    return EmbedderConfig(
        provider=provider,
        model_name=settings.embedding_model_name,
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        dimensions=settings.embedding_dimensions,
    )


def _truncate_embeddings(embeddings: np.ndarray, dimensions: int) -> np.ndarray:
    if embeddings.ndim != 2:
        raise ValueError("Embeddings must be a 2D matrix")
    if dimensions > embeddings.shape[1]:
        raise ValueError("Requested embedding dimensions exceed source embedding width")
    return embeddings[:, :dimensions]


def _normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return matrix / norms


def _normalize_vector(vector: list[float]) -> list[float]:
    array = np.asarray(vector, dtype=np.float32)
    normalized = _normalize_matrix(array.reshape(1, -1))[0]
    return normalized.astype("float32").tolist()


def _hash_embedding(text: str, dimensions: int) -> np.ndarray:
    if dimensions <= 0:
        raise ValueError("Embedding dimensions must be positive")
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], byteorder="big", signed=False)
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dimensions, dtype=np.float32)
