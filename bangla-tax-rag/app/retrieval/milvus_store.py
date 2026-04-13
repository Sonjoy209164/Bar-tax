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
    from pymilvus import MilvusClient
except Exception:  # pragma: no cover - exercised through graceful error/tests
    MilvusClient = None


class MilvusVectorStore(VectorStore):
    def __init__(self, config: VectorStoreConfig) -> None:
        if config.provider is not VectorStoreProvider.MILVUS:
            raise ValueError("MilvusVectorStore requires provider='milvus'")
        super().__init__(config)

    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        if not records:
            return
        data = [
            {
                "id": record.record_id,
                "vector": record.vector,
                "text": record.text,
                "namespace": namespace or record.namespace or self.config.namespace,
                **record.metadata,
            }
            for record in records
        ]
        self._client().upsert(collection_name=self._collection_name(), data=data)

    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        expr = _build_milvus_filter_expression(filters, namespace=namespace or self.config.namespace)
        response = self._client().search(
            collection_name=self._collection_name(),
            data=[query_vector],
            limit=top_k,
            filter=expr,
            output_fields=["text", "namespace"],
        )
        raw_matches = response[0] if response else []
        matches = [self._to_match(match) for match in raw_matches]
        return VectorSearchResult(
            provider=self.provider,
            matches=matches,
            top_k=top_k,
            namespace=namespace or self.config.namespace,
        )

    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        if not record_ids:
            return
        self._client().delete(collection_name=self._collection_name(), ids=record_ids)

    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        stats = self._client().describe_collection(collection_name=self._collection_name())
        count = stats.get("num_entities") if isinstance(stats, dict) else None
        return VectorStoreStats(
            provider=self.provider,
            index_name=self._collection_name(),
            total_vector_count=count,
            namespace=namespace or self.config.namespace,
            metadata={"raw": stats if isinstance(stats, dict) else None},
        )

    def _client(self):
        if MilvusClient is None:
            raise RuntimeError("pymilvus dependency is not installed")
        if not self.config.milvus_uri:
            raise ValueError("Milvus URI is required")
        kwargs: dict[str, Any] = {"uri": self.config.milvus_uri}
        if self.config.milvus_token:
            kwargs["token"] = self.config.milvus_token
        return MilvusClient(**kwargs)

    def _collection_name(self) -> str:
        if not self.config.milvus_collection_name:
            raise ValueError("Milvus collection name is required")
        return self.config.milvus_collection_name

    def _to_match(self, match: Any) -> VectorSearchMatch:
        entity = _read_attr(match, "entity", default={}) or {}
        return VectorSearchMatch(
            record_id=str(_read_attr(match, "id", default="")),
            score=float(_read_attr(match, "distance", default=0.0)),
            metadata={key: value for key, value in entity.items() if key not in {"text", "namespace"}},
            text=entity.get("text"),
            namespace=entity.get("namespace"),
        )


def _build_milvus_filter_expression(
    filters: dict[str, Any] | None,
    *,
    namespace: str | None = None,
) -> str | None:
    expressions: list[str] = []
    merged_filters = dict(filters or {})
    if namespace:
        merged_filters["namespace"] = namespace
    for key, value in merged_filters.items():
        if value is None:
            continue
        if isinstance(value, dict):
            for operator, operand in value.items():
                expressions.append(_build_operator_expression(key, operator, operand))
            continue
        if isinstance(value, list):
            values = ", ".join(_quote_milvus_value(item) for item in value)
            expressions.append(f"{key} in [{values}]")
            continue
        expressions.append(f"{key} == {_quote_milvus_value(value)}")
    return " and ".join(expressions) if expressions else None


def _build_operator_expression(key: str, operator: str, operand: Any) -> str:
    if operator == "$eq":
        return f"{key} == {_quote_milvus_value(operand)}"
    if operator == "$in":
        values = ", ".join(_quote_milvus_value(item) for item in operand)
        return f"{key} in [{values}]"
    if operator == "$gte":
        return f"{key} >= {_quote_milvus_value(operand)}"
    if operator == "$lte":
        return f"{key} <= {_quote_milvus_value(operand)}"
    raise ValueError(f"Unsupported Milvus filter operator: {operator}")


def _quote_milvus_value(value: Any) -> str:
    if isinstance(value, str):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return str(value)


def _read_attr(obj: Any, key: str, *, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
