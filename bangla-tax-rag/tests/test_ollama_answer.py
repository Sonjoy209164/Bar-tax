"""Tests for generate_ollama_answer in natural_answer module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.inventory.natural_answer import generate_ollama_answer


_SNIPPETS = [
    {"name": "Red Jamdani Saree", "price": 6800, "stock": 4, "attributes": {"color": "red", "fabric": "jamdani"}},
]


# ── success path ──────────────────────────────────────────────────────────────

def test_returns_natural_answer_on_success() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "message": {"content": "জি আছে! লাল জামদানি শাড়ি BDT 6,800-এ পাওয়া যাচ্ছে। এখন ৪টা স্টক আছে।"}
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        result = generate_ollama_answer(
            question="লাল শাড়ি আছে?",
            product_snippets=_SNIPPETS,
            language_hint="bangla",
        )
    assert result is not None
    assert "জামদানি" in result or "লাল" in result
    mock_post.assert_called_once()


def test_posts_to_ollama_chat_endpoint() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "message": {"content": "We have a beautiful red jamdani saree at BDT 6,800 with 4 in stock."}
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        generate_ollama_answer(
            question="red saree?",
            product_snippets=_SNIPPETS,
        )
    call_url = mock_post.call_args[0][0]
    assert "/api/chat" in call_url


def test_model_and_stream_in_payload() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "message": {"content": "We have beautiful red sarees available for BDT 6,800."}
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        generate_ollama_answer(
            question="show me sarees",
            product_snippets=_SNIPPETS,
            model="test-model",
        )
    payload = mock_post.call_args[1]["json"]
    assert payload["model"] == "test-model"
    assert payload["stream"] is False


# ── failure / degradation paths ───────────────────────────────────────────────

def test_returns_none_on_connection_error() -> None:
    with patch("httpx.post", side_effect=ConnectionError("refused")):
        result = generate_ollama_answer(
            question="red saree?",
            product_snippets=_SNIPPETS,
        )
    assert result is None


def test_returns_none_on_http_error() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
    with patch("httpx.post", return_value=mock_resp):
        result = generate_ollama_answer(
            question="red saree?",
            product_snippets=_SNIPPETS,
        )
    assert result is None


def test_returns_none_when_content_empty() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"message": {"content": ""}}
    with patch("httpx.post", return_value=mock_resp):
        result = generate_ollama_answer(
            question="red saree?",
            product_snippets=_SNIPPETS,
        )
    assert result is None


def test_returns_none_when_content_too_short() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"message": {"content": "Yes"}}
    with patch("httpx.post", return_value=mock_resp):
        result = generate_ollama_answer(
            question="red saree?",
            product_snippets=_SNIPPETS,
        )
    assert result is None


def test_returns_none_on_timeout() -> None:
    import httpx
    with patch("httpx.post", side_effect=httpx.TimeoutException("timed out")):
        result = generate_ollama_answer(
            question="red saree?",
            product_snippets=_SNIPPETS,
        )
    assert result is None


def test_fallback_param_not_leaked_as_answer() -> None:
    """When Ollama fails, returns None — not the fallback string."""
    with patch("httpx.post", side_effect=ConnectionError("refused")):
        result = generate_ollama_answer(
            question="saree?",
            product_snippets=_SNIPPETS,
            fallback="template answer here",
        )
    assert result is None  # caller decides what to do with None


def test_custom_timeout_passed_to_httpx() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "message": {"content": "We have beautiful sarees for you to browse today here."}
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        generate_ollama_answer(
            question="sarees?",
            product_snippets=_SNIPPETS,
            timeout=5.0,
        )
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs.get("timeout") == 5.0
