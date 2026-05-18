"""Tests for LLM slot extractor module (offline — no Ollama required)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.inventory.llm_slot_extractor import (
    extract_slots_via_llm,
    is_ollama_available,
    merge_llm_slots_into_fashion_slots,
)
from app.inventory.fashion_retail import FashionRetailSlots


def _mock_response(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"response": json.dumps(payload)}
    mock.raise_for_status.return_value = None
    return mock


@patch("httpx.post")
def test_extract_slots_returns_dict(mock_post: MagicMock) -> None:
    mock_post.return_value = _mock_response({
        "category": "saree",
        "color": "red",
        "fabric": "jamdani",
        "work_type": None,
        "size": None,
        "brand": None,
        "budget_max": None,
        "budget_min": None,
        "occasion": None,
        "intent": "fashion_search",
        "language": "bangla",
        "wants_in_stock": True,
    })
    result = extract_slots_via_llm("লাল জামদানি শাড়ি আছে?")
    assert result is not None
    assert result["category"] == "saree"
    assert result["color"] == "red"


@patch("httpx.post")
def test_extract_slots_strips_markdown_fence(mock_post: MagicMock) -> None:
    raw = "```json\n{\"category\": \"panjabi\", \"color\": null, \"fabric\": null, \"work_type\": null, \"size\": null, \"brand\": null, \"budget_max\": null, \"budget_min\": null, \"occasion\": null, \"intent\": \"fashion_search\", \"language\": \"banglish\", \"wants_in_stock\": false}\n```"
    mock = MagicMock()
    mock.json.return_value = {"response": raw}
    mock.raise_for_status.return_value = None
    mock_post.return_value = mock
    result = extract_slots_via_llm("panjabi dekhao")
    assert result is not None
    assert result["category"] == "panjabi"


@patch("httpx.post", side_effect=Exception("connection refused"))
def test_extract_slots_returns_none_on_failure(mock_post: MagicMock) -> None:
    result = extract_slots_via_llm("anything")
    assert result is None


def test_merge_llm_slots_regex_wins() -> None:
    regex_slots = FashionRetailSlots(category_key="saree", color="red", fabric="katan")
    llm_slots = {"category": "panjabi", "color": "blue", "fabric": "jamdani", "intent": "fashion_search", "language": "bangla"}
    merged = merge_llm_slots_into_fashion_slots(llm_slots, regex_slots)
    # regex wins on fields where it returned a value
    assert merged.category_key == "saree"
    assert merged.color == "red"
    assert merged.fabric == "katan"


def test_merge_llm_slots_fills_gaps() -> None:
    regex_slots = FashionRetailSlots(category_key=None, color=None, fabric=None)
    llm_slots = {"category": "saree", "color": "green", "fabric": "muslin", "intent": "fashion_search", "language": "bangla"}
    merged = merge_llm_slots_into_fashion_slots(llm_slots, regex_slots)
    assert merged.category_key == "saree"
    assert merged.color == "green"


def test_merge_llm_slots_none_llm_returns_regex() -> None:
    regex_slots = FashionRetailSlots(category_key="saree")
    merged = merge_llm_slots_into_fashion_slots(None, regex_slots)
    assert merged is regex_slots


@patch("httpx.get")
def test_is_ollama_available_true(mock_get: MagicMock) -> None:
    mock_get.return_value = MagicMock(status_code=200)
    assert is_ollama_available() is True


@patch("httpx.get", side_effect=Exception("offline"))
def test_is_ollama_available_false(mock_get: MagicMock) -> None:
    assert is_ollama_available() is False
