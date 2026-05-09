"""Tests for soft-confirm decoration."""
from __future__ import annotations

from app.inventory.soft_confirm import (
    decorate_with_soft_confirm,
    needs_soft_confirm,
    soft_confirm_suffix,
)


# ── needs_soft_confirm ───────────────────────────────────────────────────────

def test_high_confidence_does_not_need_soft_confirm() -> None:
    assert needs_soft_confirm(0.92, "fashion_search") is False


def test_low_confidence_does_not_need_soft_confirm() -> None:
    """Low confidence triggers clarification, not soft-confirm."""
    assert needs_soft_confirm(0.40, "fashion_search") is False


def test_medium_confidence_triggers_soft_confirm() -> None:
    assert needs_soft_confirm(0.75, "fashion_search") is True


def test_variant_intent_skips_soft_confirm() -> None:
    assert needs_soft_confirm(0.75, "fashion_variant_color") is False


def test_size_availability_skips_soft_confirm() -> None:
    assert needs_soft_confirm(0.75, "fashion_size_availability") is False


def test_policy_intent_skips_soft_confirm() -> None:
    assert needs_soft_confirm(0.70, "policy_delivery") is False


def test_order_intent_skips_soft_confirm() -> None:
    assert needs_soft_confirm(0.70, "order_place") is False


def test_clarification_intent_skips_soft_confirm() -> None:
    assert needs_soft_confirm(0.70, "fashion_clarification") is False


# ── soft_confirm_suffix language picker ──────────────────────────────────────

def test_suffix_bangla_has_bangla_chars() -> None:
    s = soft_confirm_suffix("bangla")
    assert any(ord(c) > 0x0980 for c in s)


def test_suffix_english_is_plain_ascii() -> None:
    s = soft_confirm_suffix("english")
    assert all(ord(c) < 256 for c in s)


def test_suffix_unknown_lang_falls_back_to_english() -> None:
    s_unknown = soft_confirm_suffix("hindi")
    s_english = soft_confirm_suffix("english")
    assert s_unknown == s_english


# ── decorate_with_soft_confirm ───────────────────────────────────────────────

def test_decorate_appends_suffix_in_zone() -> None:
    out = decorate_with_soft_confirm(
        "We have a red saree.", confidence=0.75, intent="fashion_search", language="english"
    )
    assert "red saree" in out
    assert "looking for" in out.lower() or "something else" in out.lower()


def test_decorate_does_not_append_outside_zone() -> None:
    out = decorate_with_soft_confirm(
        "We have a red saree.", confidence=0.95, intent="fashion_search", language="english"
    )
    assert "looking for" not in out.lower()


def test_decorate_idempotent_when_suffix_already_present() -> None:
    suffix = soft_confirm_suffix("english")
    base = f"We have a red saree. {suffix}"
    out = decorate_with_soft_confirm(base, confidence=0.75, intent="fashion_search", language="english")
    # Suffix should not appear twice
    assert out.count(suffix) == 1


def test_decorate_skips_for_clarification_intent() -> None:
    base = "What category are you looking for?"
    out = decorate_with_soft_confirm(
        base, confidence=0.70, intent="fashion_clarification", language="english"
    )
    assert out == base
