"""Tests for the clarification policy."""
from __future__ import annotations

from app.inventory.clarification import (
    HIGH_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    decide_clarification,
)
from app.inventory.fashion_retail import FashionRetailSlots


def _slots(**kw) -> FashionRetailSlots:
    """Helper — start from a default and override what the test cares about."""
    return FashionRetailSlots(**kw)


# ── high confidence: never clarify ────────────────────────────────────────────

def test_high_confidence_does_not_clarify() -> None:
    s = _slots(intent="fashion_search", category_key="saree", color_family="red", confidence=0.95)
    decision = decide_clarification(slots=s, total_matches=4)
    assert decision.should_clarify is False


def test_high_confidence_with_many_matches_but_narrowed_does_not_clarify() -> None:
    # category + color = narrowing, so even with 30 matches we just rank+show
    s = _slots(intent="fashion_search", category_key="saree", color_family="red", confidence=0.92)
    decision = decide_clarification(slots=s, total_matches=30)
    assert decision.should_clarify is False


# ── low confidence: always clarify ────────────────────────────────────────────

def test_very_low_confidence_clarifies() -> None:
    s = _slots(intent="fashion_search", confidence=0.3)
    decision = decide_clarification(slots=s, total_matches=200)
    assert decision.should_clarify is True
    assert decision.question is not None
    assert decision.reason is not None


def test_low_confidence_no_slots_clarifies_in_correct_language() -> None:
    s = _slots(intent="fashion_search", confidence=0.4, language="bangla")
    decision = decide_clarification(slots=s, total_matches=100)
    assert decision.should_clarify is True
    # Bangla question should contain at least one Bangla character
    assert any(ord(c) > 0x0980 for c in (decision.question or ""))


def test_low_confidence_banglish_clarification() -> None:
    s = _slots(intent="fashion_search", confidence=0.4, language="banglish")
    decision = decide_clarification(slots=s, total_matches=100)
    assert decision.should_clarify is True
    assert decision.question is not None
    # Banglish has no Bangla unicode but uses words like "kon", "khujchen"
    assert "khuj" in decision.question.lower() or "kon" in decision.question.lower() or "ki" in decision.question.lower()


# ── too-broad gate ────────────────────────────────────────────────────────────

def test_too_broad_only_category_clarifies() -> None:
    s = _slots(intent="fashion_search", category_key="saree", confidence=0.78)
    decision = decide_clarification(slots=s, total_matches=50)
    assert decision.should_clarify is True
    assert "too_broad" in (decision.reason or "")


def test_category_plus_color_does_not_trigger_too_broad() -> None:
    s = _slots(intent="fashion_search", category_key="saree", color_family="red", confidence=0.8)
    decision = decide_clarification(slots=s, total_matches=50)
    assert decision.should_clarify is False


# ── intent-specific bypass ────────────────────────────────────────────────────

def test_policy_intent_never_clarifies() -> None:
    s = _slots(intent="policy_delivery", confidence=0.3)
    decision = decide_clarification(slots=s, total_matches=0)
    assert decision.should_clarify is False


def test_order_intent_never_clarifies() -> None:
    s = _slots(intent="order_place", confidence=0.4)
    decision = decide_clarification(slots=s, total_matches=0)
    assert decision.should_clarify is False


# ── clarification picks the most useful missing slot ─────────────────────────

def test_clarification_asks_for_category_when_missing() -> None:
    s = _slots(intent="fashion_search", confidence=0.4, language="english")
    decision = decide_clarification(slots=s, total_matches=200)
    assert decision.missing_slot == "category"


def test_clarification_asks_for_occasion_or_color_when_only_category_known() -> None:
    s = _slots(intent="fashion_search", category_key="saree", confidence=0.5, language="english")
    decision = decide_clarification(slots=s, total_matches=80)
    assert decision.missing_slot in ("occasion_or_color", "color")


def test_category_plus_occasion_does_not_clarify_at_medium_confidence() -> None:
    # Occasion already narrows the catalog enough — don't badger the customer
    s = _slots(
        intent="fashion_search",
        category_key="saree",
        occasion="wedding",
        confidence=0.7,
        language="english",
    )
    decision = decide_clarification(slots=s, total_matches=40)
    assert decision.should_clarify is False


def test_low_confidence_with_occasion_still_clarifies() -> None:
    # Below LOW_CONFIDENCE we always ask, regardless of slots — the LLM is unsure
    s = _slots(
        intent="fashion_search",
        category_key="saree",
        occasion="wedding",
        confidence=0.45,
        language="english",
    )
    decision = decide_clarification(slots=s, total_matches=40)
    assert decision.should_clarify is True


# ── threshold sanity ──────────────────────────────────────────────────────────

def test_threshold_constants_are_ordered() -> None:
    assert HIGH_CONFIDENCE > MEDIUM_CONFIDENCE
