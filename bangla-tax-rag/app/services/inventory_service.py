from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.schemas import (
    InventoryAskRequest,
    InventoryAskResponse,
    InventoryCatalogResponse,
    InventoryDeleteResponse,
    InventoryItemRecord,
    InventorySearchFilters,
    InventorySearchHit,
    InventorySearchRequest,
    InventorySearchResponse,
    InventoryStatusResponse,
    InventoryUpsertResponse,
)
from app.core.settings import get_settings
from app.retrieval import TextEmbedder, VectorRecord, VectorStore, build_embedder, build_vector_store

_UNDER_PRICE_PATTERN = re.compile(r"(?:under|below|less than)\s*\$?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_OVER_PRICE_PATTERN = re.compile(r"(?:over|above|more than)\s*\$?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


class InventoryServiceConfig(BaseModel):
    catalog_path: str = "data/inventory/catalog.jsonl"
    namespace: str = "inventory"
    default_top_k: int = Field(default=5, ge=1, le=50)
    max_top_k: int = Field(default=20, ge=1, le=100)
    search_candidate_multiplier: int = Field(default=4, ge=1, le=20)
    low_stock_threshold: int = Field(default=10, ge=0, le=10000)


class InventoryService:
    def __init__(
        self,
        *,
        embedder: TextEmbedder,
        vector_store: VectorStore,
        config: InventoryServiceConfig | None = None,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.config = config or InventoryServiceConfig()

    def status(self) -> InventoryStatusResponse:
        items = self._load_catalog()
        rag_enabled_count = sum(1 for item in items.values() if item.include_in_rag)
        vector_stats = self.vector_store.describe(namespace=self.config.namespace)
        return InventoryStatusResponse(
            status="success",
            ready=True,
            total_items=len(items),
            rag_enabled_items=rag_enabled_count,
            vector_record_count=vector_stats.total_vector_count or 0,
            namespace=self.config.namespace,
            catalog_path=str(self._catalog_path()),
            vector_backend=self.vector_store.provider.value,
            vector_store_path=getattr(self.vector_store.config, "local_store_path", None),
        )

    def list_items(self) -> InventoryCatalogResponse:
        items = sorted(self._load_catalog().values(), key=self._catalog_sort_key, reverse=True)
        return InventoryCatalogResponse(status="success", total_items=len(items), items=items)

    def get_item(self, product_id: str) -> InventoryItemRecord | None:
        return self._load_catalog().get(product_id)

    def upsert_items(self, items: list[InventoryItemRecord]) -> InventoryUpsertResponse:
        catalog = self._load_catalog()
        rag_enabled_count = 0
        records_to_upsert: list[VectorRecord] = []
        record_ids_to_delete: list[str] = []

        for item in items:
            catalog[item.product_id] = item
            if item.include_in_rag:
                rag_enabled_count += 1
                records_to_upsert.append(self._build_vector_record(item))
            else:
                record_ids_to_delete.append(item.product_id)

        self._persist_catalog(catalog)
        if record_ids_to_delete:
            self.vector_store.delete(record_ids_to_delete, namespace=self.config.namespace)
        if records_to_upsert:
            self.vector_store.upsert(records_to_upsert, namespace=self.config.namespace)

        return InventoryUpsertResponse(
            status="success",
            upserted_count=len(items),
            rag_enabled_count=rag_enabled_count,
            total_items=len(catalog),
            namespace=self.config.namespace,
            catalog_path=str(self._catalog_path()),
        )

    def delete_items(self, product_ids: list[str]) -> InventoryDeleteResponse:
        catalog = self._load_catalog()
        deleted_ids = [product_id for product_id in product_ids if product_id in catalog]
        for product_id in deleted_ids:
            catalog.pop(product_id, None)
        self._persist_catalog(catalog)
        if deleted_ids:
            self.vector_store.delete(deleted_ids, namespace=self.config.namespace)
        return InventoryDeleteResponse(
            status="success",
            deleted_count=len(deleted_ids),
            total_items=len(catalog),
            namespace=self.config.namespace,
            catalog_path=str(self._catalog_path()),
        )

    def search(self, request: InventorySearchRequest) -> InventorySearchResponse:
        catalog = self._load_catalog()
        top_k = min(request.top_k, self.config.max_top_k)
        query_text = (request.query_text or "").strip()
        if query_text:
            hits = self._semantic_search(query_text=query_text, top_k=top_k, filters=request.filters, catalog=catalog)
        else:
            hits = self._browse_items(top_k=top_k, filters=request.filters, catalog=catalog)
        return InventorySearchResponse(
            status="success",
            query_text=query_text or None,
            total_hits=len(hits),
            applied_filters=request.filters,
            hits=hits,
        )

    def ask(self, request: InventoryAskRequest) -> InventoryAskResponse:
        effective_filters = self._merge_question_filters(
            question=request.question,
            filters=request.filters,
            low_stock_threshold=request.low_stock_threshold,
        )
        search_response = self.search(
            InventorySearchRequest(
                query_text=request.question,
                top_k=request.top_k,
                filters=effective_filters,
            )
        )
        answer = self._build_answer(
            question=request.question,
            hits=search_response.hits,
            filters=effective_filters,
            low_stock_threshold=request.low_stock_threshold,
        )
        return InventoryAskResponse(
            status="success",
            question=request.question,
            answer=answer,
            confidence_score=self._estimate_confidence(search_response.hits),
            total_hits=search_response.total_hits,
            applied_filters=effective_filters,
            hits=search_response.hits,
        )

    def _semantic_search(
        self,
        *,
        query_text: str,
        top_k: int,
        filters: InventorySearchFilters,
        catalog: dict[str, InventoryItemRecord],
    ) -> list[InventorySearchHit]:
        query_vector = self.embedder.embed_text(query_text)
        vector_filters = self._build_vector_filters(filters)
        candidate_limit = max(top_k * self.config.search_candidate_multiplier, top_k)
        result = self.vector_store.query(
            query_vector,
            top_k=candidate_limit,
            filters=vector_filters or None,
            namespace=self.config.namespace,
        )

        hits: list[InventorySearchHit] = []
        for match in result.matches:
            item = catalog.get(match.record_id)
            if item is None:
                continue
            if not self._item_matches_filters(item, filters):
                continue
            hits.append(self._build_search_hit(item=item, score=match.score))
            if len(hits) >= top_k:
                break
        return hits

    def _browse_items(
        self,
        *,
        top_k: int,
        filters: InventorySearchFilters,
        catalog: dict[str, InventoryItemRecord],
    ) -> list[InventorySearchHit]:
        items = [
            item
            for item in sorted(catalog.values(), key=self._catalog_sort_key, reverse=True)
            if self._item_matches_filters(item, filters)
        ]
        return [self._build_search_hit(item=item, score=0.0) for item in items[:top_k]]

    def _merge_question_filters(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        low_stock_threshold: int,
    ) -> InventorySearchFilters:
        merged = filters.model_copy(deep=True)
        lowered = question.casefold()

        if self._has_any_phrase(lowered, ["out of stock", "stockout", "stock out"]):
            if merged.max_stock is None:
                merged.max_stock = 0
        elif self._has_any_phrase(lowered, ["low stock", "running low", "below threshold", "limited stock"]):
            if merged.max_stock is None:
                merged.max_stock = low_stock_threshold

        under_match = _UNDER_PRICE_PATTERN.search(question)
        if under_match and merged.max_price is None:
            merged.max_price = float(under_match.group(1))

        over_match = _OVER_PRICE_PATTERN.search(question)
        if over_match and merged.min_price is None:
            merged.min_price = float(over_match.group(1))

        return merged

    def _build_answer(
        self,
        *,
        question: str,
        hits: list[InventorySearchHit],
        filters: InventorySearchFilters,
        low_stock_threshold: int,
    ) -> str:
        if not hits:
            return "I could not find any inventory items that match that request."

        lowered = question.casefold()

        if self._has_any_phrase(lowered, ["out of stock", "stockout", "stock out"]):
            zero_stock_hits = [hit for hit in hits if (hit.stock or 0) == 0]
            selected_hits = zero_stock_hits or hits
            return self._format_answer(
                intro=f"I found {len(selected_hits)} out-of-stock item(s).",
                hits=selected_hits,
            )

        if self._has_any_phrase(lowered, ["low stock", "running low", "below threshold", "limited stock"]):
            threshold = filters.max_stock if filters.max_stock is not None else low_stock_threshold
            low_stock_hits = [hit for hit in hits if hit.stock is not None and hit.stock <= threshold]
            selected_hits = low_stock_hits or hits
            return self._format_answer(
                intro=f"I found {len(selected_hits)} low-stock item(s) at or below {threshold} units.",
                hits=selected_hits,
            )

        if self._has_any_phrase(lowered, ["most expensive", "highest price", "expensive"]):
            selected_hits = sorted(
                hits,
                key=lambda item: (-1 if item.price is None else -item.price, item.name.casefold()),
            )
            return self._format_answer(
                intro="Here are the highest-priced matching items.",
                hits=selected_hits,
            )

        if self._has_any_phrase(lowered, ["cheapest", "lowest price", "least expensive"]):
            selected_hits = sorted(
                hits,
                key=lambda item: (float("inf") if item.price is None else item.price, item.name.casefold()),
            )
            return self._format_answer(
                intro="Here are the lowest-priced matching items.",
                hits=selected_hits,
            )

        return self._format_answer(
            intro=f"I found {len(hits)} matching inventory item(s).",
            hits=hits,
        )

    def _format_answer(self, *, intro: str, hits: list[InventorySearchHit], limit: int = 5) -> str:
        lines = [intro]
        for hit in hits[:limit]:
            lines.append(self._format_hit_line(hit))
        return " ".join(lines)

    def _format_hit_line(self, hit: InventorySearchHit) -> str:
        details = [f"{hit.name} (SKU {hit.sku})"]
        if hit.category:
            details.append(f"category {hit.category}")
        if hit.price is not None:
            details.append(f"price {hit.currency or 'USD'} {hit.price:.2f}")
        if hit.stock is not None:
            details.append(f"stock {hit.stock}")
        if hit.status:
            details.append(f"status {hit.status}")
        return "; ".join(details) + "."

    def _estimate_confidence(self, hits: list[InventorySearchHit]) -> float:
        if not hits:
            return 0.0
        top_score = hits[0].score
        if top_score == 0.0:
            return 0.5
        normalized = (top_score + 1.0) / 2.0
        return round(max(0.0, min(1.0, normalized)), 3)

    def _build_vector_filters(self, filters: InventorySearchFilters) -> dict[str, object]:
        vector_filters: dict[str, object] = {}
        if filters.product_ids:
            vector_filters["product_id"] = filters.product_ids
        if filters.categories:
            vector_filters["category_key"] = [category.casefold() for category in filters.categories]
        if filters.brands:
            vector_filters["brand_key"] = [brand.casefold() for brand in filters.brands]
        if filters.statuses:
            vector_filters["status_key"] = [status.casefold() for status in filters.statuses]
        stock_filter: dict[str, int] = {}
        if filters.min_stock is not None:
            stock_filter["$gte"] = filters.min_stock
        if filters.max_stock is not None:
            stock_filter["$lte"] = filters.max_stock
        if stock_filter:
            vector_filters["stock"] = stock_filter
        price_filter: dict[str, float] = {}
        if filters.min_price is not None:
            price_filter["$gte"] = filters.min_price
        if filters.max_price is not None:
            price_filter["$lte"] = filters.max_price
        if price_filter:
            vector_filters["price"] = price_filter
        return vector_filters

    def _item_matches_filters(self, item: InventoryItemRecord, filters: InventorySearchFilters) -> bool:
        if filters.rag_only and not item.include_in_rag:
            return False
        if filters.product_ids and item.product_id not in filters.product_ids:
            return False
        if filters.categories and not self._matches_text_filter(item.category, filters.categories):
            return False
        if filters.brands and not self._matches_text_filter(item.brand, filters.brands):
            return False
        if filters.statuses and not self._matches_text_filter(item.status, filters.statuses):
            return False
        if filters.tags:
            item_tags = {tag.casefold() for tag in item.tags}
            requested_tags = {tag.casefold() for tag in filters.tags}
            if not item_tags.intersection(requested_tags):
                return False
        if filters.min_stock is not None and item.stock < filters.min_stock:
            return False
        if filters.max_stock is not None and item.stock > filters.max_stock:
            return False
        if filters.min_price is not None and (item.price is None or item.price < filters.min_price):
            return False
        if filters.max_price is not None and (item.price is None or item.price > filters.max_price):
            return False
        return True

    def _build_search_hit(self, *, item: InventoryItemRecord, score: float) -> InventorySearchHit:
        return InventorySearchHit(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            category=item.category,
            brand=item.brand,
            status=item.status,
            price=item.price,
            currency=item.currency,
            stock=item.stock,
            tags=list(item.tags),
            updated_at=item.updated_at,
            snippet=self._build_snippet(item),
            score=round(score, 4),
        )

    def _build_snippet(self, item: InventoryItemRecord) -> str | None:
        for candidate in (item.short_description, item.full_description):
            if candidate:
                return candidate[:240]
        if item.attributes:
            return ", ".join(f"{key}: {value}" for key, value in sorted(item.attributes.items()))
        return None

    def _build_vector_record(self, item: InventoryItemRecord) -> VectorRecord:
        return VectorRecord(
            record_id=item.product_id,
            vector=self.embedder.embed_text(self._build_search_text(item)),
            metadata={
                "product_id": item.product_id,
                "sku": item.sku,
                "category": item.category,
                "category_key": item.category.casefold() if item.category else None,
                "brand": item.brand,
                "brand_key": item.brand.casefold() if item.brand else None,
                "status": item.status,
                "status_key": item.status.casefold() if item.status else None,
                "stock": item.stock,
                "price": item.price,
                "currency": item.currency,
                "include_in_rag": item.include_in_rag,
                "updated_at": item.updated_at,
            },
            text=self._build_search_text(item),
            namespace=self.config.namespace,
        )

    def _build_search_text(self, item: InventoryItemRecord) -> str:
        attribute_text = " ".join(f"{key} {value}" for key, value in sorted(item.attributes.items()))
        metadata_text = " ".join(f"{key} {value}" for key, value in sorted(item.metadata.items()))
        fields = [
            item.name,
            item.sku,
            item.category,
            item.brand,
            item.short_description,
            item.full_description,
            item.status,
            " ".join(item.tags),
            attribute_text,
            metadata_text,
        ]
        return " ".join(value.strip() for value in fields if isinstance(value, str) and value.strip())

    def _catalog_path(self) -> Path:
        return Path(self.config.catalog_path)

    def _load_catalog(self) -> dict[str, InventoryItemRecord]:
        catalog_path = self._catalog_path()
        if not catalog_path.exists():
            return {}
        items: dict[str, InventoryItemRecord] = {}
        with catalog_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                item = InventoryItemRecord.model_validate_json(stripped)
                items[item.product_id] = item
        return items

    def _persist_catalog(self, items: dict[str, InventoryItemRecord]) -> None:
        catalog_path = self._catalog_path()
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        with catalog_path.open("w", encoding="utf-8") as handle:
            for item in sorted(items.values(), key=self._catalog_sort_key):
                handle.write(item.model_dump_json())
                handle.write("\n")

    @staticmethod
    def _matches_text_filter(actual: str | None, expected_values: list[str]) -> bool:
        if actual is None:
            return False
        actual_key = actual.casefold()
        return actual_key in {value.casefold() for value in expected_values}

    @staticmethod
    def _has_any_phrase(text: str, phrases: list[str]) -> bool:
        return any(phrase in text for phrase in phrases)

    @staticmethod
    def _catalog_sort_key(item: InventoryItemRecord) -> tuple[str, str]:
        updated_key = item.updated_at or ""
        return (updated_key, item.name.casefold())


@lru_cache(maxsize=1)
def get_inventory_service() -> InventoryService:
    settings = get_settings()
    return InventoryService(
        embedder=build_embedder(),
        vector_store=build_vector_store(),
        config=InventoryServiceConfig(
            catalog_path=settings.inventory_catalog_path,
            namespace=settings.inventory_vector_namespace,
            default_top_k=settings.top_k,
        ),
    )
