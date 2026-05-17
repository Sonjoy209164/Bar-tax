"""Integration tests for image search wired into the inventory chat flow.

Covers:
  - InventoryService.image_search() end-to-end (trace + decision)
  - /inventory/ask answering an uploaded screenshot
  - text-only follow-up ("white ache?") resolving against the previous
    image-search variant group
  - a fresh product request after an image search is NOT hijacked by memory
"""
from __future__ import annotations

import base64
import uuid
from pathlib import Path

import pytest

from app.core.schemas import ImageSearchRequest, InventoryAskRequest
from app.inventory.conversation_state import get_state_store
from app.retrieval import (
    EmbedderConfig,
    EmbeddingProvider,
    LocalVectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
    build_embedder,
)
from app.services.inventory_service import InventoryService, InventoryServiceConfig

ROOT = Path(__file__).resolve().parents[1]
REAL_CATALOG = ROOT / "data" / "inventory" / "catalog.jsonl"
SHIRT_BLACK_IMAGE = (
    ROOT / "frontend" / "assets" / "demo_catalog" / "shirt-ribbed-polo-black" / "primary.jpg"
)


def _service(tmp_path) -> InventoryService:
    """Build a service backed by the real catalog (image search reads catalog identity)."""
    vector_store = LocalVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            local_store_path=str(tmp_path / "vectors.jsonl"),
            namespace="image-ask-test",
            dimensions=8,
        )
    )
    embedder = build_embedder(
        EmbedderConfig(
            provider=EmbeddingProvider.DETERMINISTIC,
            model_name="deterministic-test",
            dimensions=8,
            normalize=False,
        )
    )
    return InventoryService(
        embedder=embedder,
        vector_store=vector_store,
        config=InventoryServiceConfig(
            catalog_path=str(REAL_CATALOG),
            namespace="image-ask-test",
            agentic_trace_dir=str(tmp_path / "agentic_traces"),
            business_signal_path=str(tmp_path / "signals.jsonl"),
            inventory_storage_backend="jsonl",
            inventory_sqlite_path=str(tmp_path / "mirror.sqlite3"),
        ),
    )


def _black_shirt_b64() -> str:
    return base64.b64encode(SHIRT_BLACK_IMAGE.read_bytes()).decode("ascii")


def _seed_image_search_memory(session_id: str, primary_product_id: str) -> None:
    """Simulate the state left behind by a prior image-search turn."""
    get_state_store().record_turn(
        session_id=session_id,
        question="[image upload]",
        intent="image_search",
        slots={
            "variant_group_id": "ribbed-open-collar-knit-polo",
            "design_id": "vertical-ribbed-open-collar-knit",
            "color": "black",
        },
        product_ids=[primary_product_id],
        primary_product_id=primary_product_id,
        confidence=0.97,
        abstained=False,
    )


def test_image_search_method_returns_trace_and_decision(tmp_path):
    service = _service(tmp_path)
    response = service.image_search(
        ImageSearchRequest(query_text="eta ache?", image_b64=_black_shirt_b64(), top_k=5)
    )
    assert response.status == "success"
    assert response.trace_id
    assert response.decision_label in {
        "confirmed_exact",
        "confirmed_same_design_variant",
        "likely_same_design",
        "similar_style",
        "no_confident_match",
    }
    assert response.query_image_id and response.query_image_id.startswith("upload_")
    # The trace must be retrievable and carry the image-search stage block.
    trace = service.get_chat_trace(response.trace_id)
    assert trace is not None
    assert trace.execution_path == "inventory_image_search"
    assert trace.image_search is not None
    assert trace.image_search["decision_label"] == response.decision_label
    assert trace.image_search["cif_rag"]["architecture"] == "CIF-RAG"
    assert trace.image_search["cif_rag"]["plan"]["operations"]


def test_ask_with_image_is_answered_by_image_search(tmp_path):
    service = _service(tmp_path)
    response = service.ask(
        InventoryAskRequest(question="eta ache?", image_b64=_black_shirt_b64(), top_k=5)
    )
    assert response.answer_engine == "image_search"
    assert response.answer_plan.intent == "image_search"
    assert response.trace_id
    assert response.answer
    # The trace should be persisted under the same trace_id.
    trace = service.get_chat_trace(response.trace_id)
    assert trace is not None
    assert trace.image_search is not None


def test_image_followup_white_resolves_variant_group(tmp_path):
    service = _service(tmp_path)
    session_id = f"img-followup-{uuid.uuid4().hex}"
    _seed_image_search_memory(session_id, "shirt-ribbed-polo-black")

    response = service.ask(
        InventoryAskRequest(question="white ache?", session_id=session_id, top_k=6)
    )
    assert response.answer_engine == "image_search"
    assert response.memory_resolution.used_memory is True
    assert "shirt-ribbed-polo-black" in response.memory_resolution.resolved_product_ids
    assert response.answer_plan.detected_intent == "image_search"
    # The white sibling variant must surface as a recommended product.
    assert "shirt-ribbed-polo-white" in response.recommended_product_ids
    assert "white" in response.answer.casefold()


def test_image_followup_color_listing_uses_variant_group(tmp_path):
    service = _service(tmp_path)
    session_id = f"img-colors-{uuid.uuid4().hex}"
    _seed_image_search_memory(session_id, "shirt-ribbed-polo-olive")

    response = service.ask(
        InventoryAskRequest(question="ar ki ki color ache?", session_id=session_id, top_k=6)
    )
    assert response.answer_engine == "image_search"
    assert response.memory_resolution.used_memory is True
    recommended = set(response.recommended_product_ids)
    # All four ribbed-polo siblings belong to the same variant group.
    assert {"shirt-ribbed-polo-black", "shirt-ribbed-polo-grey", "shirt-ribbed-polo-white"} & recommended


def test_fresh_product_request_after_image_search_is_not_hijacked(tmp_path):
    service = _service(tmp_path)
    session_id = f"img-fresh-{uuid.uuid4().hex}"
    _seed_image_search_memory(session_id, "shirt-ribbed-polo-black")

    # Naming a different product type must start a new search, not a follow-up.
    response = service.ask(
        InventoryAskRequest(question="red saree ache?", session_id=session_id, top_k=5)
    )
    assert response.answer_engine != "image_search"


def test_is_image_variant_followup_heuristic(tmp_path):
    service = _service(tmp_path)
    assert service._is_image_variant_followup("white ache?") is True
    assert service._is_image_variant_followup("M size ache?") is True
    assert service._is_image_variant_followup("ar ki color ache?") is True
    # A fresh product type cancels the follow-up interpretation.
    assert service._is_image_variant_followup("red saree ache?") is False
