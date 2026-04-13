from __future__ import annotations

from typing import Any

from app.retrieval.vector_store_base import (
    VectorRecord,
    VectorSearchMatch,
    VectorSearchResult,
    VectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
    VectorStoreStats,
)

try:  # pragma: no cover - optional dependency
    from pinecone import Pinecone
except Exception:  # pragma: no cover - exercised through graceful error/tests
    Pinecone = None


class PineconeVectorStore(VectorStore):
    def __init__(self, config: VectorStoreConfig) -> None:
        if config.provider is not VectorStoreProvider.PINECONE:
            raise ValueError("PineconeVectorStore requires provider='pinecone'")
        super().__init__(config)

    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        vectors = [
            {
                "id": record.record_id,
                "values": record.vector,
                "metadata": {
                    **record.metadata,
                    "_text": record.text,
                },
            }
            for record in records
        ]
        if not vectors:
            return
        self._index().upsert(vectors=vectors, namespace=namespace or self.config.namespace)

    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        response = self._index().query(
            vector=query_vector,
            top_k=top_k,
            namespace=namespace or self.config.namespace,
            filter=filters,
            include_metadata=True,
        )
        raw_matches = getattr(response, "matches", None)
        if raw_matches is None and isinstance(response, dict):
            raw_matches = response.get("matches", [])
        matches = [self._to_match(match, namespace or self.config.namespace) for match in (raw_matches or [])]
        return VectorSearchResult(
            provider=self.provider,
            matches=matches,
            top_k=top_k,
            namespace=namespace or self.config.namespace,
        )

    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        if not record_ids:
            return
        self._index().delete(ids=record_ids, namespace=namespace or self.config.namespace)

    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        stats = self._index().describe_index_stats()
        namespaces = getattr(stats, "namespaces", None)
        if namespaces is None and isinstance(stats, dict):
            namespaces = stats.get("namespaces", {})
        target_namespace = namespace or self.config.namespace
        namespace_count = None
        if isinstance(namespaces, dict) and target_namespace and target_namespace in namespaces:
            namespace_stats = namespaces[target_namespace]
            if isinstance(namespace_stats, dict):
                namespace_count = namespace_stats.get("vector_count")
            else:
                namespace_count = getattr(namespace_stats, "vector_count", None)
        total_count = getattr(stats, "total_vector_count", None)
        if total_count is None and isinstance(stats, dict):
            total_count = stats.get("total_vector_count")
        return VectorStoreStats(
            provider=self.provider,
            index_name=self.config.pinecone_index_name or "",
            total_vector_count=namespace_count or total_count,
            namespace=target_namespace,
            metadata={"raw": stats if isinstance(stats, dict) else None},
        )

    def _client(self):
        if Pinecone is None:
            raise RuntimeError("pinecone dependency is not installed")
        if not self.config.pinecone_api_key:
            raise ValueError("Pinecone API key is required")
        return Pinecone(api_key=self.config.pinecone_api_key)

    def _index(self):
        if not self.config.pinecone_index_name:
            raise ValueError("Pinecone index name is required")
        client = self._client()
        if self.config.pinecone_host:
            return client.Index(host=self.config.pinecone_host)
        return client.Index(self.config.pinecone_index_name)

    def _to_match(self, match: Any, namespace: str | None) -> VectorSearchMatch:
        metadata = _read_attr(match, "metadata", default={}) or {}
        return VectorSearchMatch(
            record_id=_read_attr(match, "id", default=""),
            score=float(_read_attr(match, "score", default=0.0)),
            metadata={key: value for key, value in metadata.items() if key != "_text"},
            text=metadata.get("_text"),
            namespace=namespace,
        )


def _read_attr(obj: Any, key: str, *, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
