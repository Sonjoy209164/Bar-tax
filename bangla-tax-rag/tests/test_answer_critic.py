"""Tests for the answer critic / self-check loop."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.inventory.answer_critic import (
    CritiqueResult,
    _build_critique,
    _render_products,
    critique_answer,
)


_PRODUCTS = [
    {"name": "Red Saree", "price": 5000, "stock": 3,
     "attributes": {"color": "red", "fabric": "jamdani"}},
]


# ── _render_products ─────────────────────────────────────────────────────────

def test_render_handles_empty() -> None:
    text = _render_products([])
    assert "no products" in text.lower()


def test_render_includes_attributes() -> None:
    text = _render_products(_PRODUCTS)
    assert "Red Saree" in text
    assert "stock=3" in text


# ── _build_critique ──────────────────────────────────────────────────────────

def test_build_passes_when_severity_ok() -> None:
    c = _build_critique({"passes": True, "severity": "ok", "issues": []})
    assert c.passes is True
    assert c.severity == "ok"


def test_build_fails_when_severity_major() -> None:
    c = _build_critique({"passes": False, "severity": "major",
                         "issues": ["claimed in stock but stock=0"],
                         "suggested_fix": "Say it's out of stock."})
    assert c.passes is False
    assert c.severity == "major"
    assert "stock=0" in c.issues[0]


def test_build_minor_severity_passes_by_default() -> None:
    c = _build_critique({"severity": "minor"})
    assert c.passes is True


def test_build_invalid_severity_falls_back_to_ok() -> None:
    c = _build_critique({"severity": "catastrophic"})
    assert c.severity == "ok"


def test_build_caps_issues_at_five() -> None:
    c = _build_critique({"severity": "major", "issues": [f"i{i}" for i in range(10)]})
    assert len(c.issues) == 5


# ── critique_answer (mocked HTTP) ────────────────────────────────────────────

def test_empty_answer_immediately_fails() -> None:
    c = critique_answer(question="?", answer="", product_snippets=_PRODUCTS)
    assert c.passes is False
    assert c.severity == "major"


def test_passes_when_critic_says_ok() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": '{"passes":true,"severity":"ok","issues":[],"suggested_fix":""}'
    }
    with patch("httpx.post", return_value=mock_resp):
        c = critique_answer(
            question="red saree achhe?",
            answer="Yes, our Red Saree is BDT 5,000 with 3 in stock.",
            product_snippets=_PRODUCTS,
        )
    assert c.passes is True


def test_fails_when_critic_flags_major() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": '{"passes":false,"severity":"major","issues":["claimed wrong color"],"suggested_fix":"Use red, not blue."}'
    }
    with patch("httpx.post", return_value=mock_resp):
        c = critique_answer(
            question="red saree?",
            answer="Yes, our Blue Saree is available.",
            product_snippets=_PRODUCTS,
        )
    assert c.passes is False
    assert c.severity == "major"
    assert c.suggested_fix.startswith("Use red")


def test_treats_http_failure_as_pass() -> None:
    """If the critic itself errors, we never block — the answer goes out as-is."""
    with patch("httpx.post", side_effect=ConnectionError("refused")):
        c = critique_answer(
            question="?", answer="Some answer.", product_snippets=_PRODUCTS,
        )
    assert c.passes is True


def test_treats_invalid_json_as_pass() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"response": "garbage output not json"}
    with patch("httpx.post", return_value=mock_resp):
        c = critique_answer(
            question="?", answer="answer", product_snippets=_PRODUCTS,
        )
    assert c.passes is True
