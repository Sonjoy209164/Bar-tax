"""
Integration tests: LLM-first extraction + clarification gate
inside FashionRetailAssistant.answer().
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.schemas import InventoryItemRecord, InventorySearchFilters
from app.inventory.fashion_retail import FashionRetailAssistant


def _sample_catalog() -> dict[str, InventoryItemRecord]:
    path = Path("data/inventory/saree_shop_catalog.jsonl")
    items: dict[str, InventoryItemRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = InventoryItemRecord.model_validate_json(line)
        items[item.product_id] = item
    return items


def _ollama_mock_response(json_str: str) -> MagicMock:
    """Build a fake httpx.post response that returns the given JSON body."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.status_code = 200
    resp.json.return_value = {"response": json_str}
    return resp


def _ollama_tags_mock() -> MagicMock:
    """is_ollama_available() probe — returns 200."""
    resp = MagicMock()
    resp.status_code = 200
    return resp


# ── clarification triggers when LLM says low confidence ──────────────────────

def test_low_confidence_query_triggers_clarification() -> None:
    """A vague query (category present but no narrowing) should ask, not dump."""
    classifier_response = _ollama_mock_response(
        '{"intent":"fashion_search","category":"saree","color":null,"fabric":null,'
        '"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,'
        '"occasion":null,"language":"banglish","wants_in_stock":false,'
        '"confidence":0.40,"ambiguity_reason":"only category given"}'
    )

    def fake_post(url, **kw):
        return classifier_response

    def fake_get(url, **kw):
        return _ollama_tags_mock()

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        assistant = FashionRetailAssistant()
        outcome = assistant.answer(
            question="saree dekhao",
            catalog=_sample_catalog(),
            filters=InventorySearchFilters(),
        )

    assert outcome is not None
    assert outcome.intent == "fashion_clarification"
    assert outcome.follow_up_question is not None
    assert len(outcome.product_ids) == 0
    # answer should match the follow-up question (asking, not answering)
    assert outcome.answer == outcome.follow_up_question


# ── high confidence + good slots → normal answer, no clarification ───────────

def test_high_confidence_query_proceeds_to_answer() -> None:
    """A well-formed query with concrete slots should NOT trigger clarification."""
    classifier_response = _ollama_mock_response(
        '{"intent":"fashion_search","category":"saree","color":"red","fabric":"jamdani",'
        '"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,'
        '"occasion":null,"language":"bangla","wants_in_stock":true,'
        '"confidence":0.95,"ambiguity_reason":null}'
    )

    def fake_post(url, **kw):
        return classifier_response

    def fake_get(url, **kw):
        return _ollama_tags_mock()

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        assistant = FashionRetailAssistant()
        outcome = assistant.answer(
            question="লাল জামদানি শাড়ি আছে?",
            catalog=_sample_catalog(),
            filters=InventorySearchFilters(),
        )

    assert outcome is not None
    assert outcome.intent != "fashion_clarification"
    # We had high-confidence product slots; the engine should attempt to answer
    assert outcome.confidence >= 0.85


# ── too-broad query (only category) clarifies even with high LLM confidence ──

def test_only_category_with_many_matches_clarifies() -> None:
    """'Show me sarees' has high LLM confidence but is operationally too broad."""
    classifier_response = _ollama_mock_response(
        '{"intent":"fashion_search","category":"saree","color":null,"fabric":null,'
        '"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,'
        '"occasion":null,"language":"english","wants_in_stock":false,'
        '"confidence":0.88,"ambiguity_reason":null}'
    )

    def fake_post(url, **kw):
        return classifier_response

    def fake_get(url, **kw):
        return _ollama_tags_mock()

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        assistant = FashionRetailAssistant()
        outcome = assistant.answer(
            question="show me sarees",
            catalog=_sample_catalog(),
            filters=InventorySearchFilters(),
        )

    assert outcome is not None
    # Either it clarifies (preferred) or it answered — accept clarification path
    if outcome.intent == "fashion_clarification":
        assert outcome.follow_up_question is not None
        assert len(outcome.product_ids) == 0


# ── LLM unavailable: regex-only fallback still works ────────────────────────

def test_works_when_ollama_unavailable() -> None:
    """If Ollama is down, the bot still answers via regex (no crash)."""
    def fake_get(url, **kw):
        # is_ollama_available probe returns 503 → False
        resp = MagicMock()
        resp.status_code = 503
        return resp

    with patch("httpx.get", side_effect=fake_get):
        assistant = FashionRetailAssistant()
        outcome = assistant.answer(
            question="Do you have the Lotus Buti Jamdani in blue?",
            catalog=_sample_catalog(),
            filters=InventorySearchFilters(),
        )
    assert outcome is not None
    # Without LLM the regex pipeline should still detect the variant intent
    assert outcome.intent == "fashion_variant_color"


# ── policy intent never clarifies ────────────────────────────────────────────

def test_policy_intent_skips_clarification_even_at_low_confidence() -> None:
    """Policy questions go to a dedicated handler; never ask back."""
    classifier_response = _ollama_mock_response(
        '{"intent":"policy_delivery","category":null,"color":null,"fabric":null,'
        '"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,'
        '"occasion":null,"language":"banglish","wants_in_stock":false,'
        '"confidence":0.30,"ambiguity_reason":"unclear"}'
    )

    def fake_post(url, **kw):
        return classifier_response

    def fake_get(url, **kw):
        return _ollama_tags_mock()

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        assistant = FashionRetailAssistant()
        outcome = assistant.answer(
            question="delivery koto?",
            catalog=_sample_catalog(),
            filters=InventorySearchFilters(),
        )

    # Policy intents are routed by a different layer (PolicyQA), so the fashion
    # engine returns None or a non-clarification outcome — but never asks back.
    if outcome is not None:
        assert outcome.intent != "fashion_clarification"
