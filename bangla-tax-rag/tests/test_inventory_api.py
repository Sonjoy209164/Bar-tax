import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.retrieval import (
    EmbedderConfig,
    EmbeddingBatch,
    EmbeddingProvider,
    LocalVectorStore,
    TextEmbedder,
    VectorStoreConfig,
    VectorStoreProvider,
)
from app.services.inventory_service import InventoryService, InventoryServiceConfig


class KeywordEmbedder(TextEmbedder):
    _VOCAB = [
        "wireless",
        "headphones",
        "earbuds",
        "audio",
        "office",
        "laptop",
        "bag",
        "premium",
        "noise",
        "stock",
    ]

    def embed_texts(self, texts: list[str]) -> EmbeddingBatch:
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.casefold()
            vectors.append([float(lowered.count(token)) for token in self._VOCAB])
        return EmbeddingBatch(
            vectors=vectors,
            model_name=self.config.model_name,
            provider=self.provider,
            dimensions=len(self._VOCAB),
        )


def _build_inventory_service(tmp_path) -> InventoryService:  # type: ignore[no-untyped-def]
    vector_store = LocalVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            local_store_path=str(tmp_path / "inventory_vectors.jsonl"),
            namespace="inventory-test",
            dimensions=10,
        )
    )
    embedder = KeywordEmbedder(
        EmbedderConfig(
            provider=EmbeddingProvider.DETERMINISTIC,
            model_name="keyword-embedder",
            dimensions=10,
            normalize=False,
        )
    )
    return InventoryService(
        embedder=embedder,
        vector_store=vector_store,
        config=InventoryServiceConfig(
            catalog_path=str(tmp_path / "inventory_catalog.jsonl"),
            namespace="inventory-test",
            low_stock_threshold=10,
        ),
    )


@pytest.mark.anyio
async def test_inventory_api_end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    payload = {
        "items": [
            {
                "product_id": "prod-headphones",
                "sku": "WHP-001",
                "name": "Wireless Headphones Pro",
                "category": "Audio",
                "brand": "AudioTech",
                "short_description": "Premium wireless headphones with noise cancellation",
                "full_description": "Wireless over-ear headphones for audio enthusiasts.",
                "price": 299.99,
                "currency": "USD",
                "stock": 45,
                "status": "Active",
                "tags": ["wireless", "audio", "premium"],
                "include_in_rag": True,
                "updated_at": "2026-04-15T10:00:00Z",
            },
            {
                "product_id": "prod-earbuds",
                "sku": "EAR-002",
                "name": "Wireless Earbuds Lite",
                "category": "Audio",
                "brand": "AudioTech",
                "short_description": "Compact wireless earbuds",
                "full_description": "Wireless earbuds for audio on the go.",
                "price": 79.99,
                "currency": "USD",
                "stock": 4,
                "status": "Low Stock",
                "tags": ["wireless", "audio", "earbuds"],
                "include_in_rag": True,
                "updated_at": "2026-04-14T10:00:00Z",
            },
            {
                "product_id": "prod-backpack",
                "sku": "BAG-003",
                "name": "Leather Backpack",
                "category": "Accessories",
                "brand": "CarryWell",
                "short_description": "Leather commuter backpack",
                "price": 189.99,
                "currency": "USD",
                "stock": 32,
                "status": "Active",
                "tags": ["bag", "travel"],
                "include_in_rag": False,
                "updated_at": "2026-04-13T10:00:00Z",
            },
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        upsert_response = await client.post("/inventory/items/upsert", json=payload)
        status_response = await client.get("/inventory/status")
        list_response = await client.get("/inventory/items")
        item_response = await client.get("/inventory/items/prod-headphones")
        search_response = await client.post(
            "/inventory/search",
            json={"query_text": "wireless headphones", "top_k": 3},
        )
        ask_response = await client.post(
            "/inventory/ask",
            json={
                "question": "Show me low stock audio items",
                "top_k": 3,
                "filters": {"categories": ["Audio"]},
            },
        )
        delete_response = await client.post(
            "/inventory/items/delete",
            json={"product_ids": ["prod-earbuds"]},
        )
        missing_response = await client.get("/inventory/items/prod-earbuds")

    assert upsert_response.status_code == 200
    assert upsert_response.json()["upserted_count"] == 3
    assert upsert_response.json()["rag_enabled_count"] == 2

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["total_items"] == 3
    assert status_payload["rag_enabled_items"] == 2
    assert status_payload["vector_record_count"] == 2

    assert list_response.status_code == 200
    assert list_response.json()["total_items"] == 3

    assert item_response.status_code == 200
    assert item_response.json()["sku"] == "WHP-001"

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total_hits"] >= 1
    assert search_payload["hits"][0]["product_id"] == "prod-headphones"

    assert ask_response.status_code == 200
    ask_payload = ask_response.json()
    assert ask_payload["total_hits"] == 1
    assert "low-stock item" in ask_payload["answer"].lower()
    assert "Wireless Earbuds Lite" in ask_payload["answer"]

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_count"] == 1

    assert missing_response.status_code == 404


@pytest.mark.anyio
async def test_inventory_ask_applies_price_heuristics(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-headphones",
                        "sku": "WHP-001",
                        "name": "Wireless Headphones Pro",
                        "category": "Audio",
                        "brand": "AudioTech",
                        "short_description": "Premium wireless headphones",
                        "price": 299.99,
                        "currency": "USD",
                        "stock": 20,
                        "status": "Active",
                        "tags": ["wireless", "audio"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-headphones-max",
                        "sku": "WHP-999",
                        "name": "Wireless Headphones Max",
                        "category": "Audio",
                        "brand": "AudioTech",
                        "short_description": "Flagship wireless headphones",
                        "price": 399.99,
                        "currency": "USD",
                        "stock": 12,
                        "status": "Active",
                        "tags": ["wireless", "audio"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        ask_response = await client.post(
            "/inventory/ask",
            json={"question": "Find wireless headphones under $300", "top_k": 5},
        )

    assert ask_response.status_code == 200
    payload = ask_response.json()
    assert payload["total_hits"] == 1
    assert payload["hits"][0]["product_id"] == "prod-headphones"
    assert payload["applied_filters"]["max_price"] == 300.0


@pytest.mark.anyio
async def test_inventory_routes_are_present_in_openapi(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/inventory/status" in paths
    assert "/inventory/items/upsert" in paths
    assert "/inventory/search" in paths
    assert "/inventory/ask" in paths
