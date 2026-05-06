from __future__ import annotations

from collections.abc import Mapping
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
    from elasticsearch import Elasticsearch, NotFoundError, helpers
except Exception:  # pragma: no cover - exercised through graceful error/tests
    Elasticsearch = None
    helpers = None

    class NotFoundError(Exception):
        pass


_RESERVED_SOURCE_FIELDS = {"record_id", "namespace", "text", "vector", "metadata"}


class ElasticsearchVectorStore(VectorStore):
    def __init__(self, config: VectorStoreConfig) -> None:
        if config.provider is not VectorStoreProvider.ELASTICSEARCH:
            raise ValueError("ElasticsearchVectorStore requires provider='elasticsearch'")
        super().__init__(config)
        self._client_instance: Any | None = None

    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        if not records:
            return
        if helpers is None:
            raise RuntimeError("elasticsearch dependency is not installed")
        self._ensure_index(len(records[0].vector))
        effective_namespace = namespace or self.config.namespace
        actions = [
            {
                "_op_type": "index",
                "_index": self._index_name(),
                "_id": self._document_id(record.record_id, effective_namespace or record.namespace),
                "_source": self._to_document(record, effective_namespace or record.namespace),
            }
            for record in records
        ]
        helpers.bulk(self._client(), actions)

    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        if self.config.dimensions:
            self._ensure_index(self.config.dimensions)
        target_namespace = namespace or self.config.namespace
        filter_clauses = self._build_filter_clauses(filters, target_namespace)
        knn: dict[str, Any] = {
            "field": "vector",
            "query_vector": query_vector,
            "k": top_k,
            "num_candidates": max(top_k * 10, 50),
        }
        if filter_clauses:
            knn["filter"] = filter_clauses
        response = self._client().search(
            index=self._index_name(),
            knn=knn,
            size=top_k,
            source_excludes=["vector"],
        )
        raw_hits = _read_path(response, "hits", "hits", default=[]) or []
        matches = [self._to_match(hit, target_namespace) for hit in raw_hits]
        return VectorSearchResult(
            provider=self.provider,
            matches=matches,
            top_k=top_k,
            namespace=target_namespace,
        )

    def lexical_query(
        self,
        query_text: str,
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        client = self._client()
        index_name = self._index_name()
        if not client.indices.exists(index=index_name):
            if self.config.dimensions:
                self._ensure_index(self.config.dimensions)
            else:
                return VectorSearchResult(
                    provider=self.provider,
                    matches=[],
                    top_k=top_k,
                    namespace=namespace or self.config.namespace,
                )
        target_namespace = namespace or self.config.namespace
        filter_clauses = self._build_filter_clauses(filters, target_namespace)
        query = self._build_lexical_query(query_text=query_text, filter_clauses=filter_clauses)
        response = client.search(
            index=index_name,
            query=query,
            size=top_k,
            source_excludes=["vector"],
        )
        raw_hits = _read_path(response, "hits", "hits", default=[]) or []
        return VectorSearchResult(
            provider=self.provider,
            matches=[self._to_match(hit, target_namespace) for hit in raw_hits],
            top_k=top_k,
            namespace=target_namespace,
        )

    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        if not record_ids:
            return
        target_namespace = namespace or self.config.namespace
        client = self._client()
        index_name = self._index_name()
        if target_namespace is None:
            client.delete_by_query(
                index=index_name,
                query={"terms": {"record_id": record_ids}},
                conflicts="proceed",
                refresh=True,
            )
            return
        for record_id in record_ids:
            try:
                client.delete(index=index_name, id=self._document_id(record_id, target_namespace), refresh=True)
            except NotFoundError:
                continue

    def record_ids(self, *, namespace: str | None = None) -> list[str]:
        client = self._client()
        index_name = self._index_name()
        target_namespace = namespace or self.config.namespace
        if not client.indices.exists(index=index_name):
            return []
        filter_clauses = self._build_filter_clauses(None, target_namespace)
        query = {"bool": {"filter": filter_clauses}} if filter_clauses else {"match_all": {}}
        if helpers is not None and hasattr(helpers, "scan"):
            hits = helpers.scan(
                client,
                index=index_name,
                query={"query": query, "_source": ["record_id"]},
                size=1000,
            )
            return [
                str(source["record_id"])
                for hit in hits
                if (source := (_read_attr(hit, "_source", default={}) or {})).get("record_id") is not None
            ]
        response = client.search(
            index=index_name,
            query=query,
            size=10000,
            source_includes=["record_id"],
        )
        raw_hits = _read_path(response, "hits", "hits", default=[]) or []
        return [
            str(source["record_id"])
            for hit in raw_hits
            if (source := (_read_attr(hit, "_source", default={}) or {})).get("record_id") is not None
        ]

    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        client = self._client()
        index_name = self._index_name()
        target_namespace = namespace or self.config.namespace
        if not client.indices.exists(index=index_name):
            return VectorStoreStats(
                provider=self.provider,
                index_name=index_name,
                total_vector_count=0,
                namespace=target_namespace,
                metadata={"index_exists": False},
            )
        filter_clauses = self._build_filter_clauses(None, target_namespace)
        query = {"bool": {"filter": filter_clauses}} if filter_clauses else {"match_all": {}}
        response = client.count(index=index_name, query=query)
        return VectorStoreStats(
            provider=self.provider,
            index_name=index_name,
            total_vector_count=int(_read_attr(response, "count", default=0) or 0),
            namespace=target_namespace,
            metadata={"index_exists": True},
        )

    def _client(self):
        if self._client_instance is not None:
            return self._client_instance
        if Elasticsearch is None:
            raise RuntimeError("elasticsearch dependency is not installed")
        if not self.config.elasticsearch_url:
            raise ValueError("Elasticsearch URL is required")
        kwargs: dict[str, Any] = {"hosts": [self.config.elasticsearch_url]}
        if self.config.elasticsearch_api_key:
            kwargs["api_key"] = self.config.elasticsearch_api_key
        elif self.config.elasticsearch_username or self.config.elasticsearch_password:
            if not self.config.elasticsearch_username or not self.config.elasticsearch_password:
                raise ValueError("Both Elasticsearch username and password are required for basic auth")
            kwargs["basic_auth"] = (self.config.elasticsearch_username, self.config.elasticsearch_password)
        self._client_instance = Elasticsearch(**kwargs)
        return self._client_instance

    def _index_name(self) -> str:
        if not self.config.elasticsearch_index_name:
            raise ValueError("Elasticsearch index name is required")
        return self.config.elasticsearch_index_name

    def _document_id(self, record_id: str, namespace: str | None) -> str:
        return f"{namespace or ''}::{record_id}"

    def _ensure_index(self, dimensions: int) -> None:
        client = self._client()
        index_name = self._index_name()
        if client.indices.exists(index=index_name):
            existing_dimensions = self._existing_vector_dimensions()
            if existing_dimensions is not None and existing_dimensions != dimensions:
                raise ValueError(
                    "Elasticsearch index "
                    f"{index_name!r} has vector dimensions {existing_dimensions}, "
                    f"but this record has dimensions {dimensions}. "
                    "Create a new index or rebuild the existing index with the matching embedding model."
                )
            return
        client.indices.create(
            index=index_name,
            mappings={
                "dynamic": True,
                "properties": {
                    "namespace": {"type": "keyword"},
                    "record_id": {"type": "keyword"},
                    "product_id": {"type": "keyword"},
                    "sku": {"type": "keyword"},
                    "name": {"type": "text"},
                    "brand": {"type": "keyword"},
                    "brand_key": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "category_key": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "status_key": {"type": "keyword"},
                    "stock": {"type": "integer"},
                    "price": {"type": "float"},
                    "currency": {"type": "keyword"},
                    "include_in_rag": {"type": "boolean"},
                    "updated_at": {"type": "keyword"},
                    "text": {"type": "text"},
                    "metadata": {"type": "object", "enabled": False},
                    "vector": {
                        "type": "dense_vector",
                        "dims": dimensions,
                        "index": True,
                        "similarity": _elasticsearch_similarity(self.config.metric),
                    },
                },
            },
        )

    def _existing_vector_dimensions(self) -> int | None:
        client = self._client()
        get_mapping = getattr(client.indices, "get_mapping", None)
        if not callable(get_mapping):
            return None
        response = get_mapping(index=self._index_name())
        index_mapping = _read_attr(response, self._index_name(), default=None)
        if index_mapping is None and isinstance(response, Mapping) and response:
            index_mapping = next(iter(response.values()))
        vector_mapping = _read_path(index_mapping or {}, "mappings", "properties", "vector", default={}) or {}
        dimensions = _read_attr(vector_mapping, "dims", default=None)
        return int(dimensions) if dimensions is not None else None

    def _to_document(self, record: VectorRecord, namespace: str | None) -> dict[str, Any]:
        metadata = dict(record.metadata)
        document: dict[str, Any] = {
            "record_id": record.record_id,
            "namespace": namespace,
            "text": record.text,
            "metadata": metadata,
            "vector": record.vector,
        }
        for key, value in metadata.items():
            if key in _RESERVED_SOURCE_FIELDS:
                continue
            if _is_safe_top_level_value(value):
                document[key] = value
        return document

    def _to_match(self, hit: Any, namespace: str | None) -> VectorSearchMatch:
        source = _read_attr(hit, "_source", default={}) or {}
        metadata = dict(source.get("metadata") or {})
        for key, value in source.items():
            if key in _RESERVED_SOURCE_FIELDS or key in metadata:
                continue
            metadata[key] = value
        return VectorSearchMatch(
            record_id=str(source.get("record_id") or _record_id_from_document_id(_read_attr(hit, "_id", default=""))),
            score=float(_read_attr(hit, "_score", default=0.0) or 0.0),
            metadata=metadata,
            text=source.get("text"),
            namespace=source.get("namespace") or namespace,
        )

    def _build_filter_clauses(
        self,
        filters: dict[str, Any] | None,
        namespace: str | None,
    ) -> list[dict[str, Any]]:
        clauses: list[dict[str, Any]] = []
        if namespace is not None:
            clauses.append({"term": {"namespace": namespace}})
        for key, expected in (filters or {}).items():
            if expected is None:
                continue
            if isinstance(expected, dict):
                range_filter: dict[str, Any] = {}
                for operator, operand in expected.items():
                    if operator == "$eq":
                        clauses.append({"term": {key: operand}})
                    elif operator == "$in":
                        clauses.append({"terms": {key: list(operand)}})
                    elif operator == "$gte":
                        range_filter["gte"] = operand
                    elif operator == "$lte":
                        range_filter["lte"] = operand
                    else:
                        raise ValueError(f"Unsupported Elasticsearch filter operator: {operator}")
                if range_filter:
                    clauses.append({"range": {key: range_filter}})
                continue
            if isinstance(expected, list):
                clauses.append({"terms": {key: expected}})
                continue
            clauses.append({"term": {key: expected}})
        return clauses

    def _build_lexical_query(
        self,
        *,
        query_text: str,
        filter_clauses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        stripped_query = query_text.strip()
        should_clauses: list[dict[str, Any]] = [
            {"term": {"sku": {"value": stripped_query, "boost": 8.0}}},
            {"term": {"product_id": {"value": stripped_query, "boost": 7.0}}},
            {"match_phrase": {"name": {"query": stripped_query, "boost": 5.0}}},
            {
                "multi_match": {
                    "query": stripped_query,
                    "fields": ["name^4", "sku^5", "brand^2", "category^2", "text"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
        ]
        return {
            "bool": {
                "filter": filter_clauses,
                "should": should_clauses,
                "minimum_should_match": 1,
            }
        }


def _elasticsearch_similarity(metric: str) -> str:
    normalized = metric.strip().lower()
    if normalized in {"cosine", "dot_product", "l2_norm", "max_inner_product"}:
        return normalized
    if normalized in {"euclidean", "l2"}:
        return "l2_norm"
    raise ValueError(f"Unsupported Elasticsearch vector metric: {metric}")


def _is_safe_top_level_value(value: Any) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(item is None or isinstance(item, str | int | float | bool) for item in value)
    return False


def _record_id_from_document_id(document_id: str) -> str:
    if "::" not in document_id:
        return document_id
    return document_id.split("::", 1)[1]


def _read_path(obj: Any, *keys: str, default: Any = None) -> Any:
    value = obj
    for key in keys:
        value = _read_attr(value, key, default=default)
        if value is default:
            return default
    return value


def _read_attr(obj: Any, key: str, *, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)
