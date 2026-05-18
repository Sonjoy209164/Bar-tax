from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.settings import get_settings


class VectorStoreProvider(StrEnum):
    LOCAL = "local"
    PINECONE = "pinecone"
    MILVUS = "milvus"
    ELASTICSEARCH = "elasticsearch"


class VectorStoreConfig(BaseModel):
    provider: VectorStoreProvider
    metric: str = "cosine"
    namespace: str | None = None
    dimensions: int | None = Field(default=None, ge=1)
    local_store_path: str | None = None
    pinecone_api_key: str | None = None
    pinecone_index_name: str | None = None
    pinecone_host: str | None = None
    milvus_uri: str | None = None
    milvus_token: str | None = None
    milvus_collection_name: str | None = None
    elasticsearch_url: str | None = None
    elasticsearch_api_key: str | None = None
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_index_name: str | None = None

    @field_validator("metric")
    @classmethod
    def normalize_metric(cls, value: str) -> str:
        return value.strip().lower()


class VectorRecord(BaseModel):
    record_id: str
    vector: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)
    text: str | None = None
    namespace: str | None = None


class VectorSearchMatch(BaseModel):
    record_id: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    text: str | None = None
    namespace: str | None = None


class VectorSearchResult(BaseModel):
    provider: VectorStoreProvider
    matches: list[VectorSearchMatch] = Field(default_factory=list)
    top_k: int
    namespace: str | None = None


class VectorStoreStats(BaseModel):
    provider: VectorStoreProvider
    index_name: str
    total_vector_count: int | None = None
    namespace: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorStore(ABC):
    def __init__(self, config: VectorStoreConfig) -> None:
        self.config = config

    @property
    def provider(self) -> VectorStoreProvider:
        return self.config.provider

    @abstractmethod
    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        raise NotImplementedError

    @abstractmethod
    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        raise NotImplementedError


def build_vector_store(config: VectorStoreConfig | None = None) -> VectorStore:
    resolved_config = config or vector_store_config_from_settings()
    if resolved_config.provider is VectorStoreProvider.LOCAL:
        from app.retrieval.local_store import LocalVectorStore

        return LocalVectorStore(resolved_config)
    if resolved_config.provider is VectorStoreProvider.PINECONE:
        from app.retrieval.pinecone_store import PineconeVectorStore

        return PineconeVectorStore(resolved_config)
    if resolved_config.provider is VectorStoreProvider.MILVUS:
        from app.retrieval.milvus_store import MilvusVectorStore

        return MilvusVectorStore(resolved_config)
    if resolved_config.provider is VectorStoreProvider.ELASTICSEARCH:
        from app.retrieval.elasticsearch_store import ElasticsearchVectorStore

        return ElasticsearchVectorStore(resolved_config)
    raise ValueError(f"Unsupported vector store provider: {resolved_config.provider}")


def vector_store_config_from_settings() -> VectorStoreConfig:
    settings = get_settings()
    return VectorStoreConfig(
        provider=VectorStoreProvider(settings.vector_db.strip().lower()),
        metric=settings.vector_metric,
        namespace=settings.vector_namespace,
        dimensions=settings.embedding_dimensions,
        local_store_path=getattr(settings, "local_vector_store_path", None),
        pinecone_api_key=settings.pinecone_api_key,
        pinecone_index_name=settings.pinecone_index_name,
        pinecone_host=settings.pinecone_host,
        milvus_uri=settings.milvus_uri,
        milvus_token=settings.milvus_token,
        milvus_collection_name=settings.milvus_collection_name,
        elasticsearch_url=settings.elasticsearch_url,
        elasticsearch_api_key=settings.elasticsearch_api_key,
        elasticsearch_username=settings.elasticsearch_username,
        elasticsearch_password=settings.elasticsearch_password,
        elasticsearch_index_name=settings.elasticsearch_index_name,
    )
