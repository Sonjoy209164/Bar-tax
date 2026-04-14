from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.retrieval.vector_store_base import (
    VectorRecord,
    VectorSearchMatch,
    VectorSearchResult,
    VectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
    VectorStoreStats,
)


class LocalVectorStore(VectorStore):
    def __init__(self, config: VectorStoreConfig) -> None:
        if config.provider is not VectorStoreProvider.LOCAL:
            raise ValueError("LocalVectorStore requires provider='local'")
        super().__init__(config)
        self._records_by_key: dict[tuple[str | None, str], VectorRecord] = {}
        self._load_from_disk()

    @property
    def records(self) -> dict[tuple[str | None, str], VectorRecord]:
        return self._records_by_key

    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        if not records:
            return
        effective_namespace = namespace or self.config.namespace
        for record in records:
            stored_record = record.model_copy(update={"namespace": effective_namespace or record.namespace})
            self._records_by_key[(stored_record.namespace, stored_record.record_id)] = stored_record
        self._persist()

    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        target_namespace = namespace or self.config.namespace
        query_array = np.asarray(query_vector, dtype=np.float32)
        matches: list[VectorSearchMatch] = []
        for record in self._records_by_key.values():
            if target_namespace is not None and record.namespace != target_namespace:
                continue
            if not _record_matches_filters(record, filters):
                continue
            record_vector = np.asarray(record.vector, dtype=np.float32)
            if record_vector.shape != query_array.shape:
                continue
            score = float(np.dot(query_array, record_vector))
            matches.append(
                VectorSearchMatch(
                    record_id=record.record_id,
                    score=score,
                    metadata=dict(record.metadata),
                    text=record.text,
                    namespace=record.namespace,
                )
            )
        ranked = sorted(matches, key=lambda item: item.score, reverse=True)[:top_k]
        return VectorSearchResult(
            provider=self.provider,
            matches=ranked,
            top_k=top_k,
            namespace=target_namespace,
        )

    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        if not record_ids:
            return
        target_namespace = namespace or self.config.namespace
        if target_namespace is None:
            keys_to_delete = [key for key in self._records_by_key if key[1] in record_ids]
        else:
            keys_to_delete = [(target_namespace, record_id) for record_id in record_ids]
        changed = False
        for key in keys_to_delete:
            if key in self._records_by_key:
                changed = True
                self._records_by_key.pop(key, None)
        if changed:
            self._persist()

    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        target_namespace = namespace or self.config.namespace
        if target_namespace is None:
            total_count = len(self._records_by_key)
        else:
            total_count = sum(1 for record in self._records_by_key.values() if record.namespace == target_namespace)
        return VectorStoreStats(
            provider=self.provider,
            index_name=self._storage_path().name,
            total_vector_count=total_count,
            namespace=target_namespace,
            metadata={"storage_path": str(self._storage_path())},
        )

    def record_ids(self, *, namespace: str | None = None) -> list[str]:
        target_namespace = namespace or self.config.namespace
        return [
            record.record_id
            for record in self._records_by_key.values()
            if target_namespace is None or record.namespace == target_namespace
        ]

    def _storage_path(self) -> Path:
        storage_path = self.config.local_store_path
        if not storage_path:
            raise ValueError("Local vector store requires local_store_path")
        return Path(storage_path)

    def _load_from_disk(self) -> None:
        storage_path = self._storage_path()
        if not storage_path.exists():
            return
        with storage_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                record = VectorRecord.model_validate_json(stripped)
                self._records_by_key[(record.namespace, record.record_id)] = record

    def _persist(self) -> None:
        storage_path = self._storage_path()
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        with storage_path.open("w", encoding="utf-8") as handle:
            for record in sorted(self._records_by_key.values(), key=lambda item: ((item.namespace or ""), item.record_id)):
                handle.write(record.model_dump_json())
                handle.write("\n")


def _record_matches_filters(record: VectorRecord, filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    for key, expected in filters.items():
        actual = record.metadata.get(key)
        if isinstance(expected, dict):
            for operator, operand in expected.items():
                if not _matches_operator(actual, operator, operand):
                    return False
            continue
        if isinstance(expected, list):
            if actual not in expected:
                return False
            continue
        if actual != expected:
            return False
    return True


def _matches_operator(actual: Any, operator: str, operand: Any) -> bool:
    if operator == "$eq":
        return actual == operand
    if operator == "$in":
        return actual in operand
    if operator == "$gte":
        return actual is not None and actual >= operand
    if operator == "$lte":
        return actual is not None and actual <= operand
    raise ValueError(f"Unsupported local vector filter operator: {operator}")
