"""Tests for the semantic catalog matcher."""
from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from app.core.schemas import InventoryItemRecord
from app.inventory.semantic_matcher import (
    SemanticCatalogMatcher,
    _render_product_text,
)


def _make_item(pid: str, **overrides) -> InventoryItemRecord:
    base = {
        "product_id": pid,
        "sku": pid,
        "name": "Sample Saree",
        "category": "saree",
        "price": 5000.0,
        "stock": 3,
    }
    base.update(overrides)
    return InventoryItemRecord(**base)


# ── _render_product_text ─────────────────────────────────────────────────────

def test_render_includes_attributes() -> None:
    item = _make_item(
        "p1",
        name="Lotus Buti Jamdani",
        category="saree",
        attributes={"color": "red", "fabric": "jamdani", "occasion": "wedding"},
    )
    text = _render_product_text(item)
    assert "Lotus Buti Jamdani" in text
    assert "red" in text
    assert "jamdani" in text
    assert "wedding" in text


def test_render_includes_full_description() -> None:
    item = _make_item("p1", full_description="Hand-woven for festive occasions")
    text = _render_product_text(item)
    assert "Hand-woven" in text


def test_render_falls_back_to_short_description() -> None:
    item = _make_item("p1", short_description="Festive saree", full_description=None)
    text = _render_product_text(item)
    assert "Festive saree" in text


def test_render_handles_minimal_item() -> None:
    item = _make_item("p1", name="X", category=None, attributes={})
    text = _render_product_text(item)
    assert text  # never empty


# ── SemanticCatalogMatcher with mocked embedder ──────────────────────────────

def _mock_embedder_returning(vectors: list[list[float]], model_name: str = "mock-multi") -> MagicMock:
    embedder = MagicMock()
    batch = MagicMock()
    batch.vectors = vectors
    batch.model_name = model_name
    batch.dimensions = len(vectors[0]) if vectors else 0
    embedder.embed_texts.return_value = batch
    return embedder


def test_returns_none_when_embedder_returns_deterministic_fallback() -> None:
    """If the embedder model name signals it's the deterministic hash, treat as unavailable."""
    matcher = SemanticCatalogMatcher()
    embedder = _mock_embedder_returning([[0.1, 0.2, 0.3]], model_name="deterministic-hash")
    matcher._embedder = embedder
    catalog = {"p1": _make_item("p1")}
    result = matcher.retrieve(question="red saree", catalog=catalog)
    assert result is None
    assert matcher.is_available() is False


def test_returns_none_when_embedder_construction_fails() -> None:
    matcher = SemanticCatalogMatcher()
    # Force _get_embedder to return None
    with patch.object(SemanticCatalogMatcher, "_get_embedder", return_value=None):
        result = matcher.retrieve(question="x", catalog={"p1": _make_item("p1")})
    assert result is None


def test_empty_question_returns_empty_list() -> None:
    matcher = SemanticCatalogMatcher()
    catalog = {"p1": _make_item("p1")}
    assert matcher.retrieve(question="", catalog=catalog) == []


def test_empty_catalog_returns_empty_list() -> None:
    matcher = SemanticCatalogMatcher()
    assert matcher.retrieve(question="red saree", catalog={}) == []


def test_retrieve_picks_closest_match() -> None:
    catalog = {
        "p1": _make_item("p1", name="Red wedding saree"),
        "p2": _make_item("p2", name="Blue casual kurti"),
    }
    # Build the matcher and inject a mocked embedder
    matcher = SemanticCatalogMatcher()
    # Product embeddings: p1 close to query, p2 far
    product_vectors = [[1.0, 0.0], [0.0, 1.0]]
    query_vectors = [[1.0, 0.0]]

    def mock_embed_texts(texts):
        batch = MagicMock()
        if len(texts) == 2:
            batch.vectors = product_vectors
            batch.dimensions = 2
        else:
            batch.vectors = query_vectors
            batch.dimensions = 2
        batch.model_name = "mock-multi"
        return batch

    embedder = MagicMock()
    embedder.embed_texts.side_effect = mock_embed_texts
    matcher._embedder = embedder

    results = matcher.retrieve(question="biye-r jonno laal", catalog=catalog, top_k=2)
    assert results is not None
    assert len(results) >= 1
    assert results[0].product_id == "p1"
    assert results[0].score > 0.9


def test_deterministic_fallback_marks_unavailable() -> None:
    """If we get the deterministic embedder back, semantic match returns None."""
    matcher = SemanticCatalogMatcher()
    embedder = _mock_embedder_returning(
        [[0.1, 0.2, 0.3]], model_name="deterministic-hash"
    )
    matcher._embedder = embedder
    catalog = {"p1": _make_item("p1")}
    results = matcher.retrieve(question="x", catalog=catalog)
    assert results is None
    assert matcher.is_available() is False


def test_min_score_threshold() -> None:
    """Results below min_score should be filtered out."""
    matcher = SemanticCatalogMatcher()
    catalog = {
        "p1": _make_item("p1", name="A"),
        "p2": _make_item("p2", name="B"),
    }
    product_vectors = [[1.0, 0.0], [-1.0, 0.0]]  # p2 anti-aligned
    query_vectors = [[1.0, 0.0]]

    def mock_embed_texts(texts):
        batch = MagicMock()
        if len(texts) == 2:
            batch.vectors = product_vectors
            batch.dimensions = 2
        else:
            batch.vectors = query_vectors
            batch.dimensions = 2
        batch.model_name = "mock-multi"
        return batch

    embedder = MagicMock()
    embedder.embed_texts.side_effect = mock_embed_texts
    matcher._embedder = embedder

    results = matcher.retrieve(question="x", catalog=catalog, min_score=0.5, top_k=5)
    assert results is not None
    # Only p1 should pass the 0.5 threshold; p2 has cos sim = -1.0
    pids = [r.product_id for r in results]
    assert "p1" in pids
    assert "p2" not in pids


def test_index_rebuilds_when_catalog_changes() -> None:
    matcher = SemanticCatalogMatcher()
    embedder = _mock_embedder_returning([[1.0, 0.0]])
    matcher._embedder = embedder

    catalog_v1 = {"p1": _make_item("p1", name="V1")}
    matcher.retrieve(question="x", catalog=catalog_v1, top_k=1)
    sig_v1 = matcher._catalog_signature

    catalog_v2 = {"p1": _make_item("p1", name="V2-different-name")}
    matcher.retrieve(question="x", catalog=catalog_v2, top_k=1)
    sig_v2 = matcher._catalog_signature

    assert sig_v1 != sig_v2
