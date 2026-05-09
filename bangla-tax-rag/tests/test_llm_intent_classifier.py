"""Tests for LLM-first intent classifier."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.inventory.llm_intent_classifier import (
    ClassifiedIntent,
    classify_intent_llm,
    _build_classified_intent,
    _parse_json_lenient,
)


# ── parsing ───────────────────────────────────────────────────────────────────

def test_parse_json_lenient_clean_json() -> None:
    text = '{"intent":"fashion_search","confidence":0.9}'
    parsed = _parse_json_lenient(text)
    assert parsed == {"intent": "fashion_search", "confidence": 0.9}


def test_parse_json_lenient_with_code_fence() -> None:
    text = '```json\n{"intent":"fashion_search","confidence":0.9}\n```'
    parsed = _parse_json_lenient(text)
    assert parsed["intent"] == "fashion_search"


def test_parse_json_lenient_with_prose_around() -> None:
    text = 'Sure, here is the JSON: {"intent":"fashion_search"} hope this helps!'
    parsed = _parse_json_lenient(text)
    assert parsed["intent"] == "fashion_search"


def test_parse_json_lenient_invalid_returns_none() -> None:
    assert _parse_json_lenient("not json at all") is None
    assert _parse_json_lenient("") is None


# ── _build_classified_intent ─────────────────────────────────────────────────

def test_build_classified_intent_normalizes_strings() -> None:
    payload = {
        "intent": "fashion_search",
        "category": "Saree",
        "color": "RED",
        "confidence": 0.92,
    }
    ci = _build_classified_intent(payload)
    assert ci.intent == "fashion_search"
    assert ci.category == "saree"
    assert ci.color == "red"
    assert ci.confidence == 0.92


def test_build_classified_intent_clamps_confidence() -> None:
    ci = _build_classified_intent({"intent": "fashion_search", "confidence": 1.5})
    assert ci.confidence == 1.0
    ci2 = _build_classified_intent({"intent": "fashion_search", "confidence": -0.2})
    assert ci2.confidence == 0.0


def test_build_classified_intent_invalid_intent_falls_back_to_unknown() -> None:
    ci = _build_classified_intent({"intent": "bogus_intent", "confidence": 0.9})
    assert ci.intent == "unknown"


def test_build_classified_intent_handles_missing_fields() -> None:
    ci = _build_classified_intent({})
    assert ci.intent == "unknown"
    assert ci.category is None
    assert ci.confidence == 0.0


def test_build_classified_intent_numeric_budget() -> None:
    ci = _build_classified_intent({"intent": "fashion_search", "budget_max": "5000", "confidence": 0.8})
    assert ci.budget_max == 5000.0


def test_build_classified_intent_invalid_budget_returns_none() -> None:
    ci = _build_classified_intent({"intent": "fashion_search", "budget_max": "abc", "confidence": 0.8})
    assert ci.budget_max is None


# ── ClassifiedIntent properties ──────────────────────────────────────────────

def test_has_concrete_slot_true_when_color_set() -> None:
    ci = ClassifiedIntent(intent="fashion_search", color="red", confidence=0.9)
    assert ci.has_concrete_slot is True


def test_has_concrete_slot_false_when_all_null() -> None:
    ci = ClassifiedIntent(intent="fashion_search", confidence=0.5)
    assert ci.has_concrete_slot is False


def test_slot_count_reflects_filled_slots() -> None:
    ci = ClassifiedIntent(
        intent="fashion_search",
        category="saree",
        color="red",
        fabric="jamdani",
        confidence=0.95,
    )
    assert ci.slot_count == 3


# ── classify_intent_llm (mocked HTTP) ────────────────────────────────────────

def test_classify_intent_llm_success() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": '{"intent":"fashion_search","category":"saree","color":"red","confidence":0.95,"language":"bangla","wants_in_stock":true}'
    }
    with patch("httpx.post", return_value=mock_resp):
        ci = classify_intent_llm("লাল শাড়ি আছে?")
    assert ci is not None
    assert ci.intent == "fashion_search"
    assert ci.category == "saree"
    assert ci.color == "red"
    assert ci.confidence == 0.95


def test_classify_intent_llm_returns_none_on_http_error() -> None:
    with patch("httpx.post", side_effect=ConnectionError("refused")):
        ci = classify_intent_llm("any question")
    assert ci is None


def test_classify_intent_llm_returns_none_on_invalid_json() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"response": "this is not json"}
    with patch("httpx.post", return_value=mock_resp):
        ci = classify_intent_llm("any question")
    assert ci is None


def test_classify_intent_llm_parses_low_confidence_with_reason() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": '{"intent":"fashion_search","confidence":0.45,"ambiguity_reason":"no slots given","language":"banglish"}'
    }
    with patch("httpx.post", return_value=mock_resp):
        ci = classify_intent_llm("kichu dekhao")
    assert ci is not None
    assert ci.confidence == 0.45
    assert "no slots" in (ci.ambiguity_reason or "")
