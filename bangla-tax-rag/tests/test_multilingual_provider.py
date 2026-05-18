"""Tests for multilingual_provider module (offline — mocks sentence-transformers)."""
from unittest.mock import MagicMock, patch

import pytest

from app.retrieval.multilingual_provider import (
    _bm25_fallback,
    cosine_similarity,
    is_available,
    semantic_search,
)


def test_cosine_similarity_identical_vectors() -> None:
    v = [0.6, 0.8]
    assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-5)


def test_cosine_similarity_orthogonal_vectors() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-5)


def test_cosine_similarity_zero_vector() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_bm25_fallback_ranks_by_overlap() -> None:
    docs = [
        {"id": "a", "text": "red jamdani saree available"},
        {"id": "b", "text": "blue panjabi stock"},
        {"id": "c", "text": "saree red color fabric"},
    ]
    results = _bm25_fallback("red saree", docs, top_k=3)
    assert results[0]["id"] in ("a", "c")
    assert results[0]["score"] >= results[1]["score"]


def test_bm25_fallback_returns_top_k() -> None:
    docs = [{"id": str(i), "text": f"item {i}"} for i in range(10)]
    results = _bm25_fallback("item", docs, top_k=3)
    assert len(results) == 3


@patch("app.retrieval.multilingual_provider._load_model", return_value=None)
def test_is_available_false_when_no_model(mock_load: MagicMock) -> None:
    assert is_available() is False


@patch("app.retrieval.multilingual_provider._load_model", return_value=None)
def test_semantic_search_falls_back_to_bm25(mock_load: MagicMock) -> None:
    docs = [
        {"id": "x", "text": "blue kurti elegant"},
        {"id": "y", "text": "red saree traditional"},
    ]
    results = semantic_search("saree red", docs, top_k=2)
    assert len(results) == 2
    assert results[0]["id"] == "y"
