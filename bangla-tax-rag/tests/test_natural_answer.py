"""Tests for natural_answer module."""
import pytest

from app.inventory.natural_answer import build_natural_answer_prompt, parse_natural_answer


def test_build_prompt_returns_list_of_messages() -> None:
    messages = build_natural_answer_prompt(
        question="লাল শাড়ি আছে?",
        product_snippets=[{"name": "Red Saree", "price": 5000, "stock": 3, "attributes": {"color": "red"}}],
        language_hint="bangla",
    )
    assert isinstance(messages, list)
    assert len(messages) >= 2
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"


def test_build_prompt_includes_product_snippets() -> None:
    messages = build_natural_answer_prompt(
        question="show me sarees",
        product_snippets=[
            {"name": "Saree A", "price": 3000, "stock": 5, "attributes": {}},
            {"name": "Saree B", "price": 4500, "stock": 2, "attributes": {}},
        ],
        language_hint="english",
    )
    user_msg = messages[-1]["content"]
    assert "Saree A" in user_msg or "Saree B" in user_msg


def test_build_prompt_empty_snippets() -> None:
    messages = build_natural_answer_prompt(
        question="any panjabi?",
        product_snippets=[],
        language_hint="banglish",
    )
    assert isinstance(messages, list)
    assert len(messages) >= 2


def test_parse_natural_answer_strips_preamble() -> None:
    raw = "Sure! Here are the results:\nলাল শাড়ি পাওয়া যাচ্ছে।"
    result = parse_natural_answer(raw, fallback="fallback")
    assert "Sure!" not in result
    assert "লাল শাড়ি" in result


def test_parse_natural_answer_fallback_on_empty() -> None:
    result = parse_natural_answer("", fallback="use this instead")
    assert result == "use this instead"


def test_parse_natural_answer_truncates_at_sentence_boundary() -> None:
    long_answer = ("কিছু পণ্য আছে। " * 50).strip()
    result = parse_natural_answer(long_answer, fallback="too long")
    assert len(result) <= 620  # 600 + some boundary margin


def test_parse_natural_answer_strips_of_course_preamble() -> None:
    raw = "Of course! আমাদের কাছে সুন্দর শাড়ি আছে।"
    result = parse_natural_answer(raw, fallback="fb")
    assert not result.startswith("Of course")
