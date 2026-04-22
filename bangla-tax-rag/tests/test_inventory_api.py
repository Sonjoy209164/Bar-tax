import pytest
from httpx import ASGITransport, AsyncClient, ReadTimeout

from app.core.schemas import (
    InventoryAnswerPlan,
    InventoryAnswerVerification,
    InventoryAskRequest,
    InventoryItemRecord,
    InventorySearchRequest,
    InventorySearchHit,
)
from app.main import app
from app.retrieval import (
    EmbedderConfig,
    EmbeddingBatch,
    EmbeddingProvider,
    LocalVectorStore,
    TextEmbedder,
    VectorRecord,
    VectorStoreConfig,
    VectorStoreProvider,
)
from app.services.inventory_service import InventoryReply, InventoryService, InventoryServiceConfig


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


class SpecKeywordEmbedder(TextEmbedder):
    _VOCAB = [
        "16",
        "32",
        "1024",
        "512",
        "gb",
        "ram",
        "storage",
        "inch",
        "screen",
        "laptop",
        "creator",
        "business",
        "ultrabook",
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


def _build_inventory_service(tmp_path, *, storage_backend: str = "jsonl") -> InventoryService:  # type: ignore[no-untyped-def]
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
            agentic_trace_dir=str(tmp_path / "inventory_agentic_traces"),
            business_signal_path=str(tmp_path / "inventory_business_signals.jsonl"),
            inventory_storage_backend=storage_backend,
            inventory_sqlite_path=str(tmp_path / "inventory_mirror.sqlite3"),
        ),
    )


def _build_spec_inventory_service(tmp_path, *, storage_backend: str = "jsonl") -> InventoryService:  # type: ignore[no-untyped-def]
    vector_store = LocalVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            local_store_path=str(tmp_path / "inventory_vectors_specs.jsonl"),
            namespace="inventory-spec-test",
            dimensions=len(SpecKeywordEmbedder._VOCAB),
        )
    )
    embedder = SpecKeywordEmbedder(
        EmbedderConfig(
            provider=EmbeddingProvider.DETERMINISTIC,
            model_name="spec-keyword-embedder",
            dimensions=len(SpecKeywordEmbedder._VOCAB),
            normalize=False,
        )
    )
    return InventoryService(
        embedder=embedder,
        vector_store=vector_store,
        config=InventoryServiceConfig(
            catalog_path=str(tmp_path / "inventory_catalog_specs.jsonl"),
            namespace="inventory-spec-test",
            low_stock_threshold=10,
            agentic_trace_dir=str(tmp_path / "inventory_agentic_traces_specs"),
            business_signal_path=str(tmp_path / "inventory_business_signals_specs.jsonl"),
            inventory_storage_backend=storage_backend,
            inventory_sqlite_path=str(tmp_path / "inventory_mirror_specs.sqlite3"),
        ),
    )


def test_inventory_vector_record_normalizes_curated_spec_metadata(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = _build_inventory_service(tmp_path)
    item = InventoryItemRecord(
        product_id="prod-creator-laptop",
        sku="CMP-LTP-900",
        name="CreatorCraft 16",
        category="Computing",
        brand="CreatorCraft",
        short_description="Performance laptop for creative work.",
        price=1699.0,
        currency="USD",
        stock=5,
        status="Active",
        tags=["laptop", "creator", "premium"],
        attributes={
            "ram": "32GB",
            "storage": "1TB SSD",
            "display": "16 inch OLED",
            "connectivity": "Wi-Fi 6 and Bluetooth",
            "water_resistance": "10ATM",
            "gps": "multi-band",
            "stylus_support": "yes",
        },
        metadata={
            "raw_attributes": {
                "ram": "32GB",
                "storage": "1TB SSD",
                "display": "16 inch OLED",
                "connectivity": "Wi-Fi 6 and Bluetooth",
                "water_resistance": "10ATM",
                "gps": "multi-band",
                "stylus_support": True,
            }
        },
        include_in_rag=True,
    )

    record = service._build_vector_record(item)

    assert record.metadata["ram_gb"] == 32
    assert record.metadata["storage_gb"] == 1024
    assert record.metadata["screen_size_inch"] == 16
    assert record.metadata["connectivity"] == "wi fi 6 and bluetooth"
    assert record.metadata["water_resistance"] == "10atm"
    assert record.metadata["gps_support"] is True
    assert record.metadata["gps_mode"] == "multi band"
    assert record.metadata["stylus_support"] is True
    assert "32 gb ram" in (record.text or "")
    assert "1024 gb storage" in (record.text or "")
    assert "16 inch screen" in (record.text or "")


def test_inventory_search_uses_normalized_spec_aliases_for_vector_matches(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = _build_spec_inventory_service(tmp_path)
    service.upsert_items(
        [
            InventoryItemRecord(
                product_id="creator-1tb",
                sku="CMP-LTP-901",
                name="CreatorCraft 16 Pro",
                category="Computing",
                brand="CreatorCraft",
                short_description="16 inch creator laptop.",
                price=1699.0,
                currency="USD",
                stock=4,
                status="Active",
                tags=["laptop", "creator"],
                attributes={"ram": "32GB", "storage": "1TB SSD", "display": "16 inch OLED"},
                metadata={"raw_attributes": {"ram": "32GB", "storage": "1TB SSD", "display": "16 inch OLED"}},
                include_in_rag=True,
            ),
            InventoryItemRecord(
                product_id="creator-512gb",
                sku="CMP-LTP-902",
                name="CreatorCraft 16 Air",
                category="Computing",
                brand="CreatorCraft",
                short_description="16 inch creator laptop.",
                price=1499.0,
                currency="USD",
                stock=9,
                status="Active",
                tags=["laptop", "creator"],
                attributes={"ram": "32GB", "storage": "512GB SSD", "display": "16 inch OLED"},
                metadata={"raw_attributes": {"ram": "32GB", "storage": "512GB SSD", "display": "16 inch OLED"}},
                include_in_rag=True,
            ),
            InventoryItemRecord(
                product_id="business-14",
                sku="CMP-LTP-903",
                name="BusinessFlow 14 Ultrabook",
                category="Computing",
                brand="BusinessFlow",
                short_description="14 inch business ultrabook.",
                price=1199.0,
                currency="USD",
                stock=11,
                status="Active",
                tags=["laptop", "business", "ultrabook"],
                attributes={"ram_gb": "16", "storage_gb": "512", "screen_size": "14 inch"},
                metadata={"raw_attributes": {"ram_gb": 16, "storage_gb": 512, "screen_size": "14 inch"}},
                include_in_rag=True,
            ),
        ]
    )

    response = service.search(
        InventorySearchRequest(
            query_text="recommend a 16 inch laptop with 32GB RAM and 1024GB storage",
            top_k=3,
        )
    )

    assert [hit.product_id for hit in response.hits[:3]] == [
        "creator-1tb",
        "creator-512gb",
        "business-14",
    ]


def test_inventory_natural_prompt_uses_writer_contract_and_plan_fields(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = _build_inventory_service(tmp_path)
    hit = InventorySearchHit(
        product_id="prod-headphones",
        sku="AUD-HP-001",
        name="Auralite Flex ANC Headphones",
        category="Audio",
        brand="Auralite",
        price=249.0,
        currency="USD",
        stock=18,
        status="Active",
        tags=["audio", "wireless", "headphones", "premium"],
        snippet="Wireless noise-cancelling headphones under 300 for focused office work",
        attributes={"battery_hours": "35"},
        evidence_scores={"final_score": 0.82, "reasons": ["exact product type match: headphones"]},
        score=0.82,
    )
    reply = InventoryReply(
        answer="For this customer, I would start with Auralite Flex ANC Headphones.",
        recommended_product_ids=[hit.product_id],
        answer_plan=InventoryAnswerPlan(
            intent="sales_premium",
            primary_product_id=hit.product_id,
            excluded_product_ids=["prod-keyboard"],
            primary_reason="Primary recommendation is Auralite Flex ANC Headphones because it is an exact product type match.",
            tradeoffs=["Keep this as the premium lead; do not position nearby products as exact substitutes."],
            risk_notes=["Do not claim shipping or discounts."],
            next_best_question="Do they care more about call quality or battery life?",
            confidence_breakdown={"primary": {"final_score": 0.82}},
        ),
        verification=InventoryAnswerVerification(passed=True, checked_final_answer=True),
    )

    messages = service._build_inventory_answer_messages(
        question="Recommend premium wireless headphones under 300",
        assistant_mode="sales",
        reply_style="detailed",
        confidence_score=0.82,
        hits=[hit],
        base_reply=reply,
        conversation_history=[],
        conversation_summary=None,
        execution_path="inventory_ask",
        reasoning_summary=[],
        missing_facts=[],
        memory_resolution=None,
    )

    system_prompt = messages[0].content
    user_prompt = messages[1].content
    assert "Decision hierarchy: answer_plan is authoritative" in system_prompt
    assert "Do not choose products" in system_prompt
    assert "Never treat writer_contract.cross_sell_product_ids as substitutes" in system_prompt
    assert "Return only strict JSON" in system_prompt
    assert '"writer_contract"' in user_prompt
    assert '"required_tradeoffs"' in user_prompt
    assert '"risk_notes"' in user_prompt
    assert '"next_best_question": "Do they care more about call quality or battery life?"' in user_prompt
    assert '"excluded_product_ids": [' in user_prompt


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
    assert ask_payload["assistant_mode"] == "support"
    assert ask_payload["reply_style"] == "short"
    assert ask_payload["total_hits"] == 1
    assert "most urgent low-stock match" in ask_payload["answer"].lower()
    assert "Wireless Earbuds Lite" in ask_payload["answer"]
    assert ask_payload["recommended_product_ids"] == []

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
async def test_inventory_sales_mode_recommends_grounded_product(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-headphones-lite",
                        "sku": "WHP-010",
                        "name": "Wireless Headphones Lite",
                        "category": "Audio",
                        "brand": "AudioTech",
                        "short_description": "Affordable wireless headphones for everyday listening",
                        "price": 149.99,
                        "currency": "USD",
                        "stock": 18,
                        "status": "Active",
                        "tags": ["wireless", "audio"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-headphones-pro",
                        "sku": "WHP-900",
                        "name": "Wireless Headphones Pro Max",
                        "category": "Audio",
                        "brand": "AudioTech",
                        "short_description": "Premium wireless headphones with noise cancellation",
                        "price": 399.99,
                        "currency": "USD",
                        "stock": 11,
                        "status": "Active",
                        "tags": ["wireless", "audio", "premium"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-watch-lowquality",
                        "sku": "WW",
                        "name": "watch",
                        "category": "ww",
                        "brand": "ww",
                        "short_description": "zsdfvzv",
                        "price": 12.44,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": [],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        ask_response = await client.post(
            "/inventory/ask",
            json={
                "question": "Recommend the best premium wireless headphones for a customer",
                "top_k": 5,
                "assistant_mode": "sales",
                "reply_style": "detailed",
            },
        )

    assert ask_response.status_code == 200
    payload = ask_response.json()
    assert payload["assistant_mode"] == "sales"
    assert payload["reply_style"] == "detailed"
    assert payload["recommended_product_ids"][0] == "prod-headphones-pro"
    assert "start with Wireless Headphones Pro Max as the premium option" in payload["answer"]
    assert "Wireless Headphones Lite ready as the fallback" in payload["answer"]
    assert "watch ready as the fallback" not in payload["answer"]
    assert "grounded in the current catalog only" in payload["answer"]


@pytest.mark.anyio
async def test_inventory_sales_mode_excludes_unrelated_cross_category_fallbacks(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
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
                        "sku": "AUD-HP-001",
                        "name": "Auralite Flex ANC Headphones",
                        "category": "Audio",
                        "brand": "Auralite",
                        "short_description": "Wireless noise-cancelling headphones under 300 for focused office work",
                        "price": 249.0,
                        "currency": "USD",
                        "stock": 18,
                        "status": "Active",
                        "tags": ["audio", "wireless", "headphones", "premium"],
                        "attributes": {
                            "connectivity": "Bluetooth 5.3",
                            "battery_hours": "35",
                            "warranty_years": "2",
                        },
                        "metadata": {
                            "raw_attributes": {
                                "connectivity": "Bluetooth 5.3",
                                "battery_hours": 35,
                                "warranty_years": 2,
                            },
                            "source_of_truth": "express-postgresql",
                        },
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-keyboard",
                        "sku": "CMP-KB-002",
                        "name": "KeyForge Mechanical Keyboard",
                        "category": "Computing",
                        "brand": "KeyForge",
                        "short_description": "Wireless mechanical keyboard with tactile switches",
                        "price": 139.0,
                        "currency": "USD",
                        "stock": 17,
                        "status": "Active",
                        "tags": ["computing", "keyboard", "wireless", "premium"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-mouse",
                        "sku": "CMP-MS-003",
                        "name": "GlidePoint Wireless Mouse",
                        "category": "Computing",
                        "brand": "GlidePoint",
                        "short_description": "Silent wireless mouse for office floors",
                        "price": 49.0,
                        "currency": "USD",
                        "stock": 31,
                        "status": "Active",
                        "tags": ["computing", "mouse", "wireless"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "Recommend the best premium wireless headphones for a customer",
                "assistant_mode": "sales",
                "reply_style": "detailed",
                "answer_engine": "deterministic",
                "top_k": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_product_ids"] == ["prod-headphones"]
    assert payload["cross_sell_product_ids"] == []
    assert "KeyForge Mechanical Keyboard ready as the fallback" not in payload["answer"]
    assert "GlidePoint Wireless Mouse" not in payload["answer"]
    assert "battery life: 35 hours" in payload["answer"]
    assert payload["answer_plan"]["primary_product_id"] == "prod-headphones"
    assert payload["answer_plan"]["excluded_product_ids"] == []
    assert all(hit["product_id"] == "prod-headphones" for hit in payload["hits"])
    assert "attributes.battery_hours" in payload["answer_plan"]["metadata_used"]
    assert payload["answer_plan"]["primary_reason"]
    assert payload["answer_plan"]["next_best_question"]
    assert payload["answer_plan"]["confidence_breakdown"]["primary"]["final_score"] == payload["hits"][0]["score"]
    assert payload["verification"]["passed"] is True


@pytest.mark.anyio
async def test_inventory_support_mode_handles_small_talk_without_searching(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/inventory/ask", json={"question": "how are you", "assistant_mode": "support"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_hits"] == 0
    assert payload["recommended_product_ids"] == []
    assert payload["reply_style"] == "short"
    assert "ready to help with product questions" in payload["answer"].lower()


@pytest.mark.anyio
async def test_inventory_agentic_mode_handles_small_talk_without_searching(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/inventory/agentic/ask",
            json={
                "question": "hello",
                "assistant_mode": "sales",
                "reply_style": "detailed",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_path"] == "inventory_agentic_conversation"
    assert payload["retrieval_steps_used"] == 0
    assert payload["total_hits"] == 0
    assert payload["recommended_product_ids"] == []
    assert "recommend the right product" in payload["answer"].lower()
    assert "retrieval and agentic tool use were skipped" in " ".join(payload["reasoning_summary"]).lower()


@pytest.mark.anyio
async def test_inventory_route_prefers_normal_rag_for_direct_catalog_question(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/inventory/route",
            json={
                "question": "show me some watches",
                "assistant_mode": "support",
                "reply_style": "short",
                "available_data_domains": ["catalog"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_path"] == "normal_rag"
    assert payload["normal_rag_contract"]["implementation_status"] == "implemented"
    assert payload["agentic_contract"]["implementation_status"] == "implemented"
    assert payload["agentic_contract"]["endpoint"] == "/inventory/agentic/ask"
    assert payload["signals"]["detected_intent"] == "product_search"
    assert payload["signals"]["question_family"] == "exact_lookup"
    assert payload["signals"]["family_confidence"] >= 0.78
    assert payload["signals"]["simple_catalog_lookup"] is True
    assert "catalog/support question" in payload["reason_summary"].lower()


@pytest.mark.anyio
async def test_inventory_route_escalates_complex_internal_question_to_agentic(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/inventory/route",
            json={
                "question": "Why are audio sales dropping this month and what should we restock first across categories?",
                "audience": "manager",
                "prefer_fast_response": False,
                "available_data_domains": ["catalog", "inventory_snapshots", "sales", "orders"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_path"] == "agentic"
    assert payload["signals"]["question_family"] == "planning_agentic_workflow"
    assert payload["signals"]["family_confidence"] >= 0.9
    assert payload["signals"]["needs_historical_data"] is True
    assert payload["signals"]["needs_cross_system_data"] is True
    assert payload["signals"]["needs_root_cause_reasoning"] is True
    assert payload["signals"]["needs_workflow_action"] is True
    assert payload["agentic_contract"]["endpoint"] == "/inventory/agentic/ask"
    assert payload["missing_data_domains"] == []


@pytest.mark.anyio
async def test_inventory_route_classifies_diagnosis_question_family(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/inventory/route",
            json={
                "question": "Why are premium earbud returns increasing this quarter?",
                "audience": "manager",
                "prefer_fast_response": False,
                "available_data_domains": ["catalog", "returns", "sales"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_path"] == "agentic"
    assert payload["signals"]["question_family"] == "diagnosis_root_cause"
    assert payload["signals"]["detected_intent"] == "business_analysis"
    assert payload["signals"]["family_confidence"] >= 0.84
    assert payload["signals"]["needs_root_cause_reasoning"] is True


@pytest.mark.anyio
async def test_inventory_agentic_endpoint_returns_traceable_response(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-watch-low",
                        "sku": "ACC-WAT-002",
                        "name": "TrailMark Essential Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Entry smart watch with lightweight notifications and health basics",
                        "price": 129.0,
                        "currency": "USD",
                        "stock": 4,
                        "status": "Low Stock",
                        "tags": ["watch", "wearable"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        agentic_response = await client.post(
            "/inventory/agentic/ask",
            json={
                "question": "show me some watches",
                "assistant_mode": "support",
                "reply_style": "short",
                "max_reasoning_steps": 3,
            },
        )

    assert agentic_response.status_code == 200
    payload = agentic_response.json()
    assert payload["execution_path"] == "inventory_agentic"
    assert payload["retrieval_steps_used"] >= 1
    assert payload["trace_id"]
    assert all(hit["product_id"] in {"prod-watch", "prod-watch-low"} for hit in payload["hits"])
    assert "Watch" in payload["answer"]
    assert payload["reasoning_summary"]


@pytest.mark.anyio
async def test_inventory_agentic_trace_and_status_endpoints(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-mic",
                        "sku": "AUD-MIC-004",
                        "name": "VoxCast USB Podcast Microphone",
                        "category": "Audio",
                        "brand": "VoxCast",
                        "short_description": "Cardioid USB microphone for podcasts and webinars",
                        "price": 159.0,
                        "currency": "USD",
                        "stock": 11,
                        "status": "Active",
                        "tags": ["audio", "microphone"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        ask_response = await client.post(
            "/inventory/agentic/ask",
            json={
                "question": "tell me about VoxCast USB Podcast Microphone",
                "assistant_mode": "support",
                "reply_style": "detailed",
            },
        )
        trace_id = ask_response.json()["trace_id"]
        trace_response = await client.get(f"/inventory/agentic/trace/{trace_id}")
        chat_trace_response = await client.get(f"/inventory/chat/trace/{trace_id}")
        status_response = await client.get("/inventory/agentic/status")

    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["trace_id"] == trace_id
    assert trace_payload["execution_path"] == "inventory_agentic"
    assert trace_payload["route_decision"]["recommended_path"] == "normal_rag"
    assert trace_payload["route_decision"]["signals"]["question_family"] == "exact_lookup"
    assert trace_payload["retrieval_steps"]
    assert "VoxCast USB Podcast Microphone" in trace_payload["final_answer"]

    assert chat_trace_response.status_code == 200
    chat_trace_payload = chat_trace_response.json()
    assert chat_trace_payload["trace_id"] == trace_id
    assert chat_trace_payload["execution_path"] == "inventory_agentic"
    assert chat_trace_payload["route_decision"]["recommended_path"] == "normal_rag"
    assert chat_trace_payload["route_decision"]["signals"]["question_family"] == "exact_lookup"
    assert chat_trace_payload["retrieval_steps"]
    assert chat_trace_payload["reasoning_summary"]
    assert chat_trace_payload["retrieved_product_ids"] == ["prod-mic"]
    assert chat_trace_payload["reranked_product_ids"] == ["prod-mic"]
    assert "VoxCast USB Podcast Microphone" in chat_trace_payload["final_answer"]

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["ready"] is True
    assert status_payload["trace_dir"].endswith("inventory_agentic_traces")


@pytest.mark.anyio
async def test_inventory_agentic_short_circuits_no_match_or_abstain_questions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        ask_response = await client.post(
            "/inventory/agentic/ask",
            json={
                "question": "budget",
                "assistant_mode": "support",
                "reply_style": "detailed",
            },
        )
        trace_id = ask_response.json()["trace_id"]
        trace_response = await client.get(f"/inventory/agentic/trace/{trace_id}")
        chat_trace_response = await client.get(f"/inventory/chat/trace/{trace_id}")

    assert ask_response.status_code == 200
    ask_payload = ask_response.json()
    assert ask_payload["execution_path"] == "inventory_agentic_no_match_or_abstain"
    assert ask_payload["retrieval_steps_used"] == 0
    assert ask_payload["total_hits"] == 0
    assert ask_payload["hits"] == []
    assert ask_payload["abstained"] is True
    assert "grounded catalog evidence" in (ask_payload["abstention_reason"] or "").lower()

    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["execution_path"] == "inventory_agentic_no_match_or_abstain"
    assert trace_payload["route_decision"]["signals"]["question_family"] == "no_match_or_abstain"
    assert trace_payload["retrieval_steps"] == []

    assert chat_trace_response.status_code == 200
    chat_trace_payload = chat_trace_response.json()
    assert chat_trace_payload["execution_path"] == "inventory_agentic_no_match_or_abstain"
    assert chat_trace_payload["route_decision"]["signals"]["question_family"] == "no_match_or_abstain"
    assert chat_trace_payload["retrieved_product_ids"] == []
    assert chat_trace_payload["reranked_product_ids"] == []


@pytest.mark.anyio
async def test_inventory_support_mode_summarizes_matches_naturally(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-mic",
                        "sku": "AUD-MIC-004",
                        "name": "VoxCast USB Podcast Microphone",
                        "category": "Audio",
                        "brand": "VoxCast",
                        "short_description": "Cardioid USB microphone for podcasts and webinars",
                        "price": 159.00,
                        "currency": "USD",
                        "stock": 11,
                        "status": "Active",
                        "tags": ["audio", "microphone"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-headphone",
                        "sku": "AUD-HP-001",
                        "name": "Auralite Flex ANC Headphones",
                        "category": "Audio",
                        "brand": "Auralite",
                        "short_description": "Wireless noise-cancelling headphones under 300 for focused office work",
                        "price": 249.00,
                        "currency": "USD",
                        "stock": 18,
                        "status": "Active",
                        "tags": ["audio", "headphones"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-chair",
                        "sku": "OFF-CHR-004",
                        "name": "ErgoMesh Pro Chair",
                        "category": "Office",
                        "brand": "ErgoMesh",
                        "short_description": "Premium ergonomic office chair with lumbar tuning",
                        "price": 549.00,
                        "currency": "USD",
                        "stock": 3,
                        "status": "Low Stock",
                        "tags": ["office", "chair", "premium"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={"question": "show premium office products", "assistant_mode": "support", "top_k": 5},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_hits"] >= 1
    assert "strongest matches are" in payload["answer"].lower()
    assert "ErgoMesh Pro Chair" in payload["answer"]


@pytest.mark.anyio
async def test_inventory_support_mode_anchors_explicit_product_terms(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-headphone",
                        "sku": "AUD-HP-001",
                        "name": "Auralite Flex ANC Headphones",
                        "category": "Audio",
                        "brand": "Auralite",
                        "short_description": "Wireless noise-cancelling headphones under 300 for focused office work",
                        "price": 249.0,
                        "currency": "USD",
                        "stock": 18,
                        "status": "Active",
                        "tags": ["audio", "headphones"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={"question": "show me some watches", "assistant_mode": "support", "top_k": 5},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["hits"][0]["product_id"] == "prod-watch"
    assert all(hit["product_id"] == "prod-watch" for hit in payload["hits"])
    assert "TrailMark Smart Watch" in payload["answer"]
    assert payload["answer_plan"]["detected_intent"] == "product_search"
    assert payload["answer_plan"]["product_type"] == "watch"
    assert payload["answer_plan"]["product_family"] == "wearable"


@pytest.mark.anyio
async def test_inventory_support_mode_rejects_unmatched_exact_lookup_queries(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-dock",
                        "sku": "CMP-DK-004",
                        "name": "DockHub 4K Triple Display Station",
                        "category": "Computing",
                        "brand": "DockHub",
                        "short_description": "USB-C docking station for laptop fleets and multi-monitor office desks",
                        "price": 229.0,
                        "currency": "USD",
                        "stock": 5,
                        "status": "Low Stock",
                        "tags": ["computing", "dock", "usb-c", "workstation"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={"question": "do you have any bike?", "assistant_mode": "support", "top_k": 5},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_hits"] == 0
    assert payload["hits"] == []
    assert "exact catalog match for bike" in payload["answer"].lower()
    assert payload["answer_plan"]["detected_intent"] == "product_search"
    assert payload["answer_plan"]["product_type"] == "bike"
    assert payload["answer_plan"]["abstain"] is True


@pytest.mark.anyio
async def test_inventory_support_mode_clarifies_no_match_route_questions(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-dock",
                        "sku": "CMP-DK-004",
                        "name": "DockHub 4K Triple Display Station",
                        "category": "Computing",
                        "brand": "DockHub",
                        "short_description": "USB-C docking station for laptop fleets and multi-monitor office desks",
                        "price": 229.0,
                        "currency": "USD",
                        "stock": 5,
                        "status": "Low Stock",
                        "tags": ["computing", "dock", "usb-c", "workstation"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "budget",
                "assistant_mode": "support",
                "reply_style": "detailed",
                "top_k": 5,
            },
        )
        payload = response.json()
        trace_response = await client.get(f"/inventory/chat/trace/{payload['trace_id']}")

    assert response.status_code == 200
    assert payload["abstained"] is False
    assert payload["total_hits"] == 0
    assert payload["hits"] == []
    assert payload["answer_plan"]["intent"] == "support_no_match"
    assert "i need one more detail" in payload["answer"].lower()
    assert payload["follow_up_question"] is not None
    assert "budget or preferred brand" in payload["follow_up_question"].lower()

    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["route_decision"]["question_family"] == "no_match_or_abstain"
    assert trace_payload["total_hits"] == 0
    assert trace_payload["retrieved_product_ids"] == ["prod-watch", "prod-dock"]


@pytest.mark.anyio
async def test_inventory_support_mode_abstains_for_non_inventory_no_match_questions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "write me a poem about rain",
                "assistant_mode": "support",
                "reply_style": "short",
                "top_k": 5,
            },
        )
        payload = response.json()
        trace_response = await client.get(f"/inventory/chat/trace/{payload['trace_id']}")

    assert response.status_code == 200
    assert payload["abstained"] is True
    assert payload["total_hits"] == 0
    assert payload["hits"] == []
    assert payload["follow_up_question"] is None
    assert "supported inventory question" in payload["answer"].lower()
    assert "supported inventory question" in (payload["abstention_reason"] or "").lower()
    assert payload["answer_plan"]["intent"] == "support_no_match"
    assert payload["answer_plan"]["abstain"] is True

    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["route_decision"]["question_family"] == "no_match_or_abstain"
    assert trace_payload["abstained"] is True


@pytest.mark.anyio
async def test_inventory_support_mode_handles_direct_product_detail_requests(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-monitor",
                        "sku": "AUD-MON-005",
                        "name": "Auralite Pro Monitor Pair",
                        "category": "Audio",
                        "brand": "Auralite",
                        "short_description": "Reference monitor speakers for editing suites and premium content desks",
                        "price": 399.0,
                        "currency": "USD",
                        "stock": 7,
                        "status": "Active",
                        "tags": ["audio", "monitors"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-headphone",
                        "sku": "AUD-HP-001",
                        "name": "Auralite Flex ANC Headphones",
                        "category": "Audio",
                        "brand": "Auralite",
                        "short_description": "Wireless noise-cancelling headphones under 300 for focused office work",
                        "price": 249.0,
                        "currency": "USD",
                        "stock": 18,
                        "status": "Active",
                        "tags": ["audio", "headphones"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "tell me about Auralite Pro Monitor Pair",
                "assistant_mode": "support",
                "reply_style": "detailed",
                "top_k": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["hits"][0]["product_id"] == "prod-monitor"
    assert payload["answer"].startswith("Auralite Pro Monitor Pair is")
    assert "The current price is USD 399.00." in payload["answer"]
    assert "There are 7 unit(s) in stock right now." in payload["answer"]
    assert payload["follow_up_question"] is not None


@pytest.mark.anyio
async def test_inventory_sales_mode_asks_for_clarification_on_ambiguous_request(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-audio",
                        "sku": "AUD-100",
                        "name": "Studio Headphones",
                        "category": "Audio",
                        "brand": "Signal",
                        "short_description": "Closed-back headphones for focused listening",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 14,
                        "status": "Active",
                        "tags": ["audio", "headphones"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-office",
                        "sku": "OFF-100",
                        "name": "Standing Desk Converter",
                        "category": "Office",
                        "brand": "WorkRise",
                        "short_description": "Compact standing desk converter",
                        "price": 259.0,
                        "currency": "USD",
                        "stock": 8,
                        "status": "Low Stock",
                        "tags": ["office", "desk"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "recommend something",
                "assistant_mode": "sales",
                "reply_style": "detailed",
                "top_k": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["follow_up_question"] is not None
    assert "i need one more detail" in payload["answer"].lower()
    assert "budget, premium feel, or immediate availability" in payload["follow_up_question"].lower()


@pytest.mark.anyio
async def test_inventory_sales_mode_handles_price_objection(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-premium-laptop",
                        "sku": "CMP-900",
                        "name": "Nimbus 14 Business Ultrabook",
                        "category": "Computing",
                        "brand": "Nimbus",
                        "short_description": "Lightweight 14 inch laptop for managers and analysts",
                        "price": 1199.0,
                        "currency": "USD",
                        "stock": 8,
                        "status": "Low Stock",
                        "tags": ["computing", "laptop", "business", "premium"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-value-laptop",
                        "sku": "CMP-500",
                        "name": "Nimbus 13 Essential Laptop",
                        "category": "Computing",
                        "brand": "Nimbus",
                        "short_description": "Lower-cost business laptop for everyday work",
                        "price": 799.0,
                        "currency": "USD",
                        "stock": 16,
                        "status": "Active",
                        "tags": ["computing", "laptop", "business"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "This is too expensive, what should I say to the customer?",
                "assistant_mode": "sales",
                "reply_style": "detailed",
                "top_k": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_product_ids"][0] == "prod-value-laptop"
    assert "too expensive" in payload["answer"].lower()
    assert "Nimbus 13 Essential Laptop" in payload["answer"]
    assert payload["follow_up_question"] is not None


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
    assert "/inventory/agentic/status" in paths
    assert "/inventory/agentic/ask" in paths
    assert "/inventory/agentic/ask/stream" in paths
    assert "/inventory/items/upsert" in paths
    assert "/inventory/search" in paths
    assert "/inventory/route" in paths
    assert "/inventory/sync/status" in paths
    assert "/inventory/sync/validate" in paths
    assert "/inventory/sync/rebuild" in paths
    assert "/inventory/production/status" in paths
    assert "/inventory/business/status" in paths
    assert "/inventory/business/signals" in paths
    assert "/inventory/business/signals/upsert" in paths
    assert "/inventory/chat/trace/{trace_id}" in paths
    assert "/inventory/ask" in paths
    assert "/inventory/ask/stream" in paths


@pytest.mark.anyio
async def test_inventory_ask_stream_returns_sse_events(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    service.upsert_items(
        [
            InventoryItemRecord(
                product_id="prod-watch",
                sku="WAT-001",
                name="TrailMark Smart Watch",
                category="Wearables",
                brand="TrailMark",
                short_description="Smart watch for fitness tracking",
                price=199.0,
                currency="USD",
                stock=7,
                status="Active",
                tags=["watch", "wearable"],
                include_in_rag=True,
            )
        ]
    )

    response = await routes_inventory.ask_inventory_stream(
        InventoryAskRequest(
            question="Tell me about the TrailMark watch",
            assistant_mode="sales",
            reply_style="short",
            answer_engine="deterministic",
            top_k=3,
        )
    )
    body_chunks: list[str] = []
    async for chunk in response.body_iterator:
        body_chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    body = "".join(body_chunks)

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert "event: status" in body
    assert "event: metadata" in body
    assert "event: answer_delta" in body
    assert "event: final" in body
    assert "TrailMark Smart Watch" in body
    assert '"trace_id"' in body


@pytest.mark.anyio
async def test_inventory_sqlite_storage_persists_catalog_and_business_signals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path, storage_backend="sqlite")
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Smart watch for fitness tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 7,
                        "status": "Active",
                        "tags": ["watch", "wearable"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        await client.post(
            "/inventory/business/signals/upsert",
            json={
                "signals": [
                    {
                        "product_id": "prod-watch",
                        "period_end": "2026-04-15",
                        "units_sold": 22,
                        "inventory_on_hand": 7,
                        "demand_score": 0.7,
                    }
                ]
            },
        )
        status_response = await client.get("/inventory/status")
        production_response = await client.get("/inventory/production/status")

    reloaded_service = _build_inventory_service(tmp_path, storage_backend="sqlite")

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["storage_backend"] == "sqlite"
    assert status_payload["storage_path"].endswith("inventory_mirror.sqlite3")

    assert production_response.status_code == 200
    production_payload = production_response.json()
    assert production_payload["storage_backend"] == "sqlite"
    assert production_payload["production_ready"] is False
    assert any(issue["code"] == "local_vector_backend" for issue in production_payload["issues"])

    assert reloaded_service.get_item("prod-watch") is not None
    business_signals = reloaded_service.list_business_signals(product_id="prod-watch")
    assert business_signals.total_signals == 1
    assert business_signals.signals[0].units_sold == 22


@pytest.mark.anyio
async def test_inventory_business_signal_endpoints(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        upsert_response = await client.post(
            "/inventory/business/signals/upsert",
            json={
                "signals": [
                    {
                        "product_id": "prod-mic",
                        "period_start": "2026-04-01",
                        "period_end": "2026-04-15",
                        "units_sold": 64,
                        "revenue": 10176.0,
                        "order_count": 48,
                        "return_count": 2,
                        "return_rate": 0.03,
                        "gross_margin": 3358.0,
                        "gross_margin_rate": 0.33,
                        "inventory_on_hand": 2,
                        "inventory_snapshot_at": "2026-04-15T10:00:00Z",
                        "supplier_id": "sup-audio",
                        "supplier_name": "Audio Supply Co",
                        "supplier_lead_time_days": 21,
                        "supplier_risk_score": 0.35,
                        "customer_segments": ["podcasters", "webinar teams"],
                        "demand_score": 0.91,
                        "updated_at": "2026-04-15T10:00:00Z",
                    }
                ]
            },
        )
        status_response = await client.get("/inventory/business/status")
        list_response = await client.get("/inventory/business/signals", params={"product_id": "prod-mic"})

    assert upsert_response.status_code == 200
    assert upsert_response.json()["upserted_count"] == 1
    assert upsert_response.json()["total_signals"] == 1

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["ready"] is True
    assert status_payload["product_count"] == 1
    assert set(status_payload["domains_available"]) == {
        "customers",
        "inventory_snapshots",
        "margins",
        "orders",
        "returns",
        "sales",
        "suppliers",
    }

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total_signals"] == 1
    assert list_payload["signals"][0]["product_id"] == "prod-mic"
    assert list_payload["signals"][0]["customer_segments"] == ["podcasters", "webinar teams"]


@pytest.mark.anyio
async def test_inventory_agentic_uses_business_signals_for_restock_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-mic",
                        "sku": "AUD-MIC-004",
                        "name": "VoxCast USB Podcast Microphone",
                        "category": "Audio",
                        "brand": "VoxCast",
                        "short_description": "Cardioid USB microphone for podcasts and webinars",
                        "price": 159.0,
                        "currency": "USD",
                        "stock": 2,
                        "status": "Low Stock",
                        "tags": ["audio", "microphone"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-headphones",
                        "sku": "AUD-HP-001",
                        "name": "Auralite Flex ANC Headphones",
                        "category": "Audio",
                        "brand": "Auralite",
                        "short_description": "Wireless headphones for office calls",
                        "price": 249.0,
                        "currency": "USD",
                        "stock": 8,
                        "status": "Low Stock",
                        "tags": ["audio", "headphones"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        await client.post(
            "/inventory/business/signals/upsert",
            json={
                "signals": [
                    {
                        "product_id": "prod-mic",
                        "period_start": "2026-04-01",
                        "period_end": "2026-04-15",
                        "units_sold": 64,
                        "order_count": 48,
                        "inventory_on_hand": 2,
                        "supplier_lead_time_days": 21,
                        "supplier_risk_score": 0.35,
                        "gross_margin_rate": 0.33,
                        "demand_score": 0.91,
                    },
                    {
                        "product_id": "prod-headphones",
                        "period_start": "2026-04-01",
                        "period_end": "2026-04-15",
                        "units_sold": 16,
                        "order_count": 12,
                        "inventory_on_hand": 8,
                        "supplier_lead_time_days": 7,
                        "gross_margin_rate": 0.28,
                        "demand_score": 0.4,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/agentic/ask",
            json={
                "question": "What should I restock first to prevent stockout?",
                "assistant_mode": "support",
                "reply_style": "detailed",
                "max_reasoning_steps": 3,
            },
        )
        trace_response = await client.get(f"/inventory/chat/trace/{response.json()['trace_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_path"] == "inventory_agentic"
    assert payload["recommended_product_ids"][0] == "prod-mic"
    assert "Business-tool read" in payload["answer"]
    assert "VoxCast USB Podcast Microphone" in payload["answer"]
    assert "sold quantity 64" in payload["answer"]
    assert "supplier lead time 21 day(s)" in payload["answer"]
    assert not any("Missing data domain" in fact for fact in payload["missing_facts"])

    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert any(step["action"] == "business_signal_analysis" for step in trace_payload["retrieval_steps"])
    assert trace_payload["retrieval_steps"][-1]["action"] == "business_signal_analysis"
    assert "Business signal tool" in " ".join(trace_payload["reasoning_summary"])


@pytest.mark.anyio
async def test_inventory_ask_returns_debuggable_chat_trace(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-mic",
                        "sku": "AUD-MIC-004",
                        "name": "VoxCast USB Podcast Microphone",
                        "category": "Audio",
                        "brand": "VoxCast",
                        "short_description": "Cardioid USB microphone for podcasts and webinars",
                        "price": 159.0,
                        "currency": "USD",
                        "stock": 11,
                        "status": "Active",
                        "tags": ["audio", "microphone"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        ask_response = await client.post(
            "/inventory/ask",
            json={
                "question": "tell me about VoxCast USB Podcast Microphone",
                "assistant_mode": "support",
                "reply_style": "detailed",
            },
        )
        trace_id = ask_response.json()["trace_id"]
        trace_response = await client.get(f"/inventory/chat/trace/{trace_id}")

    assert ask_response.status_code == 200
    ask_payload = ask_response.json()
    assert ask_payload["trace_id"]

    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["trace_id"] == trace_id
    assert trace_payload["request_id"] == trace_id
    assert trace_payload["execution_path"] == "inventory_ask"
    assert trace_payload["question"] == ask_payload["question"]
    assert trace_payload["final_answer"] == ask_payload["answer"]
    assert trace_payload["answer_engine"] == ask_payload["answer_engine"]
    assert trace_payload["latency_ms"] >= 0
    assert trace_payload["intent"] in {"exact_lookup", "product_detail", "product_search"}
    assert trace_payload["preferences"]["product_type"] == "microphone"
    assert trace_payload["retrieved_product_ids"] == ["prod-mic"]
    assert trace_payload["reranked_product_ids"] == ["prod-mic"]
    assert trace_payload["answer_plan"]["primary_product_id"] == "prod-mic"
    assert trace_payload["verification"]["checked_final_answer"] is True
    assert trace_payload["fallback_reason"] is None


@pytest.mark.anyio
async def test_inventory_sync_status_and_validate_endpoints(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                        "updated_at": "2026-04-15T10:00:00Z",
                    },
                    {
                        "product_id": "prod-internal",
                        "sku": "INT-001",
                        "name": "Internal Only Item",
                        "category": "Internal",
                        "brand": "Ops",
                        "short_description": "Internal item not included in RAG",
                        "price": 10.0,
                        "currency": "USD",
                        "stock": 1,
                        "status": "Active",
                        "tags": ["internal"],
                        "include_in_rag": False,
                        "updated_at": "2026-04-15T10:00:00Z",
                    },
                ]
            },
        )
        status_response = await client.get("/inventory/sync/status")
        valid_response = await client.post(
            "/inventory/sync/validate",
            json={"source_product_ids": ["prod-watch", "prod-internal"]},
        )
        missing_response = await client.post(
            "/inventory/sync/validate",
            json={"source_product_ids": ["prod-watch", "prod-internal", "prod-missing"]},
        )
        stale_response = await client.post(
            "/inventory/sync/validate",
            json={
                "source_items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 189.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                        "updated_at": "2026-04-15T10:00:00Z",
                    }
                ]
            },
        )

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["catalog_count"] == 2
    assert status_payload["rag_enabled_count"] == 1
    assert status_payload["vector_ids_available"] is True
    assert status_payload["vector_synced"] is True
    assert status_payload["missing_vector_ids"] == []

    assert valid_response.status_code == 200
    valid_payload = valid_response.json()
    assert valid_payload["valid"] is True
    assert valid_payload["missing_in_catalog"] == []
    assert valid_payload["extra_in_catalog"] == []
    assert valid_payload["missing_vector_ids"] == []

    assert missing_response.status_code == 200
    missing_payload = missing_response.json()
    assert missing_payload["valid"] is False
    assert missing_payload["missing_in_catalog"] == ["prod-missing"]
    assert any(issue["code"] == "missing_in_catalog" for issue in missing_payload["issues"])

    assert stale_response.status_code == 200
    stale_payload = stale_response.json()
    assert stale_payload["valid"] is False
    assert stale_payload["stale_catalog_product_ids"] == ["prod-watch"]
    assert stale_payload["extra_in_catalog"] == ["prod-internal"]


@pytest.mark.anyio
async def test_inventory_sync_rebuild_repairs_vector_drift(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                        "updated_at": "2026-04-15T10:00:00Z",
                    }
                ]
            },
        )

        service.vector_store.delete(["prod-watch"], namespace=service.config.namespace)
        service.vector_store.upsert(
            [
                VectorRecord(
                    record_id="stale-vector",
                    vector=[0.0] * 10,
                    metadata={"product_id": "stale-vector"},
                    text="stale record",
                    namespace=service.config.namespace,
                )
            ],
            namespace=service.config.namespace,
        )

        drift_response = await client.get("/inventory/sync/status")
        rebuild_response = await client.post("/inventory/sync/rebuild")

    assert drift_response.status_code == 200
    drift_payload = drift_response.json()
    assert drift_payload["vector_synced"] is False
    assert drift_payload["missing_vector_ids"] == ["prod-watch"]
    assert drift_payload["stale_vector_ids"] == ["stale-vector"]

    assert rebuild_response.status_code == 200
    rebuild_payload = rebuild_response.json()
    assert rebuild_payload["ready"] is True
    assert rebuild_payload["rebuilt_count"] == 1
    assert rebuild_payload["deleted_vector_count"] == 1
    assert rebuild_payload["vector_synced"] is True
    assert rebuild_payload["missing_vector_ids"] == []
    assert rebuild_payload["stale_vector_ids"] == []
    assert rebuild_payload["catalog_count"] == 1
    assert rebuild_payload["rag_enabled_count"] == 1
    assert rebuild_payload["namespace"] == service.config.namespace


@pytest.mark.anyio
async def test_inventory_sync_status_reports_catalog_quality_issues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-mystery",
                        "sku": "MYS-001",
                        "name": "Mystery Bundle",
                        "currency": "USD",
                        "stock": 5,
                        "status": "Active",
                        "metadata": {"": "missing key"},
                        "include_in_rag": True,
                    }
                ]
            },
        )
        response = await client.get("/inventory/sync/status")

    assert response.status_code == 200
    payload = response.json()
    issue_codes = {issue["code"] for issue in payload["issues"]}
    assert payload["ready"] is True
    assert payload["invalid_catalog_product_ids"] == ["prod-mystery"]
    assert "missing_category" in issue_codes
    assert "missing_price" in issue_codes
    assert "invalid_metadata" in issue_codes
    assert "empty_description" in issue_codes
    assert "missing_product_type" in issue_codes
    assert "weak_rag_text" in issue_codes


@pytest.mark.anyio
async def test_inventory_ask_uses_natural_answer_engine_when_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    service.config.natural_answers_enabled = True
    service.config.natural_answer_min_confidence = 0.0
    monkeypatch.setattr(
        service,
        "_run_inventory_answer_model",
        lambda **kwargs: (
            '{"answer":"I do have a strong watch option for you. TrailMark Smart Watch is available at USD 199.00 with 10 units in stock.",'
            ' "follow_up_question":"Do you want a cheaper watch or the strongest fitness-focused option?",'
            ' "abstained": false,'
            ' "abstention_reason": null}'
        ),
    )
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "show me some watches",
                "assistant_mode": "support",
                "reply_style": "short",
                "answer_engine": "natural",
                "conversation_summary": "User is browsing watches for a fitness-oriented use case.",
                "conversation_history": [
                    {"role": "user", "content": "I need a watch."},
                    {"role": "assistant", "content": "I can help you narrow that down."},
                ],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_engine"] == "natural"
    assert payload["abstained"] is False
    assert "TrailMark Smart Watch is available" in payload["answer"]
    assert payload["follow_up_question"] == "Do you want a cheaper watch or the strongest fitness-focused option?"


@pytest.mark.anyio
async def test_inventory_ask_keeps_exact_no_match_abstention_when_natural_mode_requested(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    service.config.natural_answers_enabled = True
    service.config.natural_answer_min_confidence = 0.0
    monkeypatch.setattr(
        service,
        "_run_inventory_answer_model",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("Natural model should not run for exact no-match requests.")),
    )
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "do you have any bike?",
                "assistant_mode": "support",
                "answer_engine": "natural",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_engine"] == "deterministic"
    assert payload["abstained"] is True
    assert payload["total_hits"] == 0
    assert payload["hits"] == []
    assert "exact catalog match for bike" in payload["answer"].lower()
    assert "exact catalog match for bike" in (payload["abstention_reason"] or "").lower()


@pytest.mark.anyio
async def test_inventory_ask_falls_back_when_natural_answer_fails_final_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    service.config.natural_answers_enabled = True
    service.config.natural_answer_min_confidence = 0.0
    monkeypatch.setattr(
        service,
        "_run_inventory_answer_model",
        lambda **kwargs: (
            '{"answer":"TrailMark Smart Watch is available at USD 999.00 with 10 units in stock.",'
            ' "follow_up_question":null,'
            ' "abstained": false,'
            ' "abstention_reason": null}'
        ),
    )
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "show me some watches",
                "assistant_mode": "support",
                "answer_engine": "natural",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_engine"] == "deterministic"
    assert "USD 999.00" not in payload["answer"]
    assert payload["verification"]["checked_final_answer"] is True
    assert payload["verification"]["passed"] is True


@pytest.mark.anyio
async def test_inventory_ask_falls_back_when_natural_answer_times_out(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    service.config.natural_answers_enabled = True
    service.config.natural_answer_min_confidence = 0.0
    service.config.natural_answer_timeout_seconds = 7.0
    monkeypatch.setattr(
        service,
        "_run_inventory_answer_model",
        lambda **kwargs: (_ for _ in ()).throw(ReadTimeout("timed out")),
    )
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    }
                ]
            },
        )
        ask_response = await client.post(
            "/inventory/ask",
            json={
                "question": "show me some watches",
                "assistant_mode": "support",
                "answer_engine": "natural",
            },
        )
        trace_id = ask_response.json()["trace_id"]
        trace_response = await client.get(f"/inventory/chat/trace/{trace_id}")

    assert ask_response.status_code == 200
    ask_payload = ask_response.json()
    assert ask_payload["answer_engine"] == "deterministic"
    assert ask_payload["abstained"] is False
    assert "TrailMark Smart Watch" in ask_payload["answer"]

    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["answer_engine"] == "deterministic"
    assert trace_payload["fallback_reason"] == "Natural answer model timed out after 7s; deterministic fallback was used."


@pytest.mark.anyio
async def test_inventory_ask_resolves_follow_up_reference_from_memory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-laptop",
                        "sku": "CMP-LAP-001",
                        "name": "Nimbus 14 Business Ultrabook",
                        "category": "Computing",
                        "brand": "Nimbus",
                        "short_description": "Lightweight 14 inch laptop for managers",
                        "price": 1199.0,
                        "currency": "USD",
                        "stock": 8,
                        "status": "Active",
                        "tags": ["computing", "laptop"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "tell me more about the first one",
                "assistant_mode": "support",
                "reply_style": "detailed",
                "focused_product_ids": ["prod-watch"],
                "active_filters": {"categories": ["Wearables"]},
                "last_answer_plan": {
                    "primary_product_id": "prod-watch",
                    "alternative_product_ids": [],
                    "cross_sell_product_ids": [],
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["memory_resolution"]["used_memory"] is True
    assert payload["memory_resolution"]["resolved_product_ids"] == ["prod-watch"]
    assert payload["applied_filters"]["product_ids"] == ["prod-watch"]
    assert payload["hits"][0]["product_id"] == "prod-watch"
    assert "TrailMark Smart Watch" in payload["answer"]


@pytest.mark.anyio
async def test_inventory_ask_ignores_memory_for_new_explicit_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from app.api import routes_inventory

    service = _build_inventory_service(tmp_path)
    monkeypatch.setattr(routes_inventory, "get_inventory_service", lambda: service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/inventory/items/upsert",
            json={
                "items": [
                    {
                        "product_id": "prod-watch",
                        "sku": "ACC-WAT-001",
                        "name": "TrailMark Smart Watch",
                        "category": "Wearables",
                        "brand": "TrailMark",
                        "short_description": "Fitness watch with heart-rate and GPS tracking",
                        "price": 199.0,
                        "currency": "USD",
                        "stock": 10,
                        "status": "Active",
                        "tags": ["watch", "wearable", "fitness"],
                        "include_in_rag": True,
                    },
                    {
                        "product_id": "prod-laptop",
                        "sku": "CMP-LAP-001",
                        "name": "Nimbus 14 Business Ultrabook",
                        "category": "Computing",
                        "brand": "Nimbus",
                        "short_description": "Lightweight 14 inch laptop for managers",
                        "price": 1199.0,
                        "currency": "USD",
                        "stock": 8,
                        "status": "Active",
                        "tags": ["computing", "laptop"],
                        "include_in_rag": True,
                    },
                ]
            },
        )
        response = await client.post(
            "/inventory/ask",
            json={
                "question": "show me laptops",
                "assistant_mode": "support",
                "focused_product_ids": ["prod-watch"],
                "active_filters": {"categories": ["Wearables"]},
                "last_answer_plan": {"primary_product_id": "prod-watch"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["memory_resolution"]["used_memory"] is False
    assert payload["applied_filters"]["product_ids"] == []
    assert payload["hits"][0]["product_id"] == "prod-laptop"
