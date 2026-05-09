"""Tests for the LLM reasoner."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.schemas import InventoryItemRecord
from app.inventory.llm_reasoner import (
    ReasonedSelection,
    _build_selection,
    _parse_json_lenient,
    _render_candidates,
    reason_over_candidates,
)


def _make_item(pid: str, **overrides) -> InventoryItemRecord:
    base = {
        "product_id": pid,
        "sku": pid,
        "name": "Saree",
        "price": 5000.0,
        "stock": 3,
    }
    base.update(overrides)
    return InventoryItemRecord(**base)


# ── parsing ──────────────────────────────────────────────────────────────────

def test_parse_strips_code_fence() -> None:
    raw = '```json\n{"selected_product_ids":["p1"],"confidence":0.9,"none_fit":false,"reasoning":"x"}\n```'
    parsed = _parse_json_lenient(raw)
    assert parsed["selected_product_ids"] == ["p1"]


def test_parse_extracts_json_amid_prose() -> None:
    raw = 'Sure! {"selected_product_ids":["p1"],"confidence":0.9,"none_fit":false,"reasoning":"x"} okay?'
    parsed = _parse_json_lenient(raw)
    assert parsed["confidence"] == 0.9


def test_parse_returns_none_on_invalid() -> None:
    assert _parse_json_lenient("nope") is None


# ── _build_selection ─────────────────────────────────────────────────────────

def test_build_selection_filters_invalid_ids() -> None:
    payload = {
        "selected_product_ids": ["p1", "FAKE", "p2"],
        "confidence": 0.85,
        "none_fit": False,
        "reasoning": "matches occasion + color",
    }
    sel = _build_selection(payload, valid_ids={"p1", "p2", "p3"})
    assert sel.selected_product_ids == ["p1", "p2"]
    assert sel.confidence == 0.85
    assert sel.none_fit is False


def test_build_selection_clamps_confidence() -> None:
    sel = _build_selection({"confidence": 1.5, "selected_product_ids": ["p1"]}, valid_ids={"p1"})
    assert sel.confidence == 1.0


def test_build_selection_none_fit_when_empty() -> None:
    sel = _build_selection({"selected_product_ids": [], "confidence": 0.0}, valid_ids=set())
    assert sel.none_fit is True


def test_build_selection_caps_at_five_picks() -> None:
    sel = _build_selection(
        {"selected_product_ids": [f"p{i}" for i in range(10)]},
        valid_ids={f"p{i}" for i in range(10)},
    )
    assert len(sel.selected_product_ids) == 5


# ── _render_candidates ──────────────────────────────────────────────────────

def test_render_includes_product_id_name_price_stock() -> None:
    items = [_make_item("p1", name="Red Saree", price=5000.0, stock=2,
                        attributes={"color": "red", "fabric": "jamdani"})]
    block = _render_candidates(items)
    assert "p1" in block
    assert "Red Saree" in block
    assert "5,000" in block
    assert "stock=2" in block
    assert "color=red" in block


# ── reason_over_candidates (mocked HTTP) ─────────────────────────────────────

def test_reason_returns_selection_on_success() -> None:
    items = [_make_item("p1"), _make_item("p2")]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": '{"selected_product_ids":["p1"],"reasoning":"matches color and stock","confidence":0.88,"none_fit":false}'
    }
    with patch("httpx.post", return_value=mock_resp):
        sel = reason_over_candidates(question="red saree?", candidates=items)
    assert sel is not None
    assert sel.selected_product_ids == ["p1"]
    assert sel.confidence == 0.88
    assert "matches" in sel.reasoning


def test_reason_returns_none_fit_when_no_match() -> None:
    items = [_make_item("p1")]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": '{"selected_product_ids":[],"reasoning":"none of these are wedding-grade","confidence":0.4,"none_fit":true}'
    }
    with patch("httpx.post", return_value=mock_resp):
        sel = reason_over_candidates(question="wedding saree?", candidates=items)
    assert sel.none_fit is True
    assert sel.selected_product_ids == []


def test_reason_returns_none_on_http_error() -> None:
    items = [_make_item("p1")]
    with patch("httpx.post", side_effect=ConnectionError("refused")):
        sel = reason_over_candidates(question="?", candidates=items)
    assert sel is None


def test_reason_returns_none_on_invalid_json() -> None:
    items = [_make_item("p1")]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"response": "this is not json"}
    with patch("httpx.post", return_value=mock_resp):
        sel = reason_over_candidates(question="?", candidates=items)
    assert sel is None


def test_reason_handles_empty_candidates_without_calling_llm() -> None:
    sel = reason_over_candidates(question="?", candidates=[])
    assert sel is not None
    assert sel.none_fit is True
    assert sel.selected_product_ids == []


def test_reason_passes_customer_context_to_prompt() -> None:
    items = [_make_item("p1")]
    captured_payload = {}

    def capture(url, **kw):
        captured_payload["json"] = kw.get("json", {})
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": '{"selected_product_ids":["p1"],"reasoning":"fits","confidence":0.9,"none_fit":false}'
        }
        return resp

    with patch("httpx.post", side_effect=capture):
        reason_over_candidates(
            question="?", candidates=items, customer_context="Customer often asks about red."
        )
    prompt = captured_payload["json"]["prompt"]
    assert "Customer often asks about red" in prompt
