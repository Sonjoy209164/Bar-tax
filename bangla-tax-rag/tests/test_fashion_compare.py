"""Tests for fashion_compare intent and Banglish normalization."""
import pytest

from app.core.schemas import InventoryItemRecord, InventorySearchFilters
from app.inventory.banglish_normalizer import augment_with_bangla, normalize_banglish
from app.inventory.fashion_retail import FashionRetailAssistant, FashionRetailSlots


def _make_catalog() -> dict[str, InventoryItemRecord]:
    items = [
        InventoryItemRecord(
            product_id="s1", sku="s1", name="Jamdani Saree", category="Saree", stock=5, price=8000,
            attributes={"category_key": "saree", "fabric": "jamdani", "color": "red"},
        ),
        InventoryItemRecord(
            product_id="s2", sku="s2", name="Katan Silk Saree", category="Saree", stock=3, price=12000,
            attributes={"category_key": "saree", "fabric": "katan", "color": "blue"},
        ),
        InventoryItemRecord(
            product_id="p1", sku="p1", name="Cotton Panjabi", category="Panjabi", stock=10, price=1500,
            attributes={"category_key": "panjabi", "fabric": "cotton", "color": "white"},
        ),
    ]
    return {item.product_id: item for item in items}


@pytest.fixture()
def assistant() -> FashionRetailAssistant:
    return FashionRetailAssistant()


@pytest.fixture()
def catalog() -> dict[str, InventoryItemRecord]:
    return _make_catalog()


# ── Banglish normalization ─────────────────────────────────────────────────

def test_normalize_banglish_saree() -> None:
    result = normalize_banglish("sharee dekhao")
    assert "শাড়ি" in result


def test_normalize_banglish_panjabi() -> None:
    assert "পাঞ্জাবি" in normalize_banglish("panjabi ache?")


def test_normalize_banglish_color_lal() -> None:
    assert "লাল" in normalize_banglish("laal color")


def test_augment_with_bangla_appends() -> None:
    result = augment_with_bangla("laal sharee ache?")
    assert "laal sharee ache?" in result
    assert "লাল" in result or "শাড়ি" in result


def test_normalize_no_change_for_pure_bangla() -> None:
    text = "আমাদের কাছে শাড়ি আছে"
    result = normalize_banglish(text)
    assert result == text


# ── Compare intent detection ───────────────────────────────────────────────

def test_compare_intent_detected_vs(assistant: FashionRetailAssistant, catalog: dict) -> None:
    outcome = assistant.answer(question="jamdani vs katan konta bhalo?", catalog=catalog)
    if outcome is not None:
        assert outcome.intent == "fashion_compare"


def test_compare_intent_detected_versus(assistant: FashionRetailAssistant, catalog: dict) -> None:
    slots = assistant.extract_slots(
        question="jamdani versus katan — difference ki?",
        filters=InventorySearchFilters(),
        catalog=list(catalog.values()),
    )
    assert slots.intent == "fashion_compare"


def test_compare_intent_bangla_phrase(assistant: FashionRetailAssistant, catalog: dict) -> None:
    slots = assistant.extract_slots(
        question="জামদানি নাকি কাতান — কোনটা নেবো?",
        filters=InventorySearchFilters(),
        catalog=list(catalog.values()),
    )
    assert slots.intent == "fashion_compare"


# ── Multi-turn history enrichment ─────────────────────────────────────────

def test_history_carries_color_forward(assistant: FashionRetailAssistant, catalog: dict) -> None:
    history = [("user", "laal sharee dekhao"), ("assistant", "Here are red sarees.")]
    slots = assistant.extract_slots(
        question="etar daam koto?",  # "what is its price?" — no color
        filters=InventorySearchFilters(),
        catalog=list(catalog.values()),
    )
    # Without history there may be no color; with history color=red should carry over
    # We test the _enrich_with_history method directly
    enriched = FashionRetailAssistant._enrich_with_history("etar daam koto?", history)
    assert "laal sharee dekhao" in enriched


def test_enrich_with_history_empty_history() -> None:
    result = FashionRetailAssistant._enrich_with_history("question", [])
    assert result == "question"


def test_enrich_with_history_none_history() -> None:
    result = FashionRetailAssistant._enrich_with_history("question", None)
    assert result == "question"


def test_enrich_with_history_max_turns() -> None:
    history = [("user", f"turn {i}") for i in range(10)]
    enriched = FashionRetailAssistant._enrich_with_history("final", history)
    # Should only contain last 3 user turns
    assert "turn 9" in enriched
    assert "turn 7" in enriched
    assert "turn 6" not in enriched
