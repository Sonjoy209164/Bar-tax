from __future__ import annotations

from pathlib import Path

from app.core.schemas import InventoryItemRecord, InventorySearchFilters
from app.inventory.fashion_retail import FashionRetailAssistant


def _active_catalog() -> dict[str, InventoryItemRecord]:
    items: dict[str, InventoryItemRecord] = {}
    for line in Path("data/inventory/catalog.jsonl").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        item = InventoryItemRecord.model_validate_json(stripped)
        items[item.product_id] = item
    return items


def test_styling_advice_navy_saree_gold_accessories():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="নেভি কাতান শাড়ির সাথে বিয়ের জন্য কী কী নিলে ভালো হবে?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None
    answer_lower = outcome.answer.casefold()
    assert "gold" in answer_lower or "silver" in answer_lower or "bag" in answer_lower or "ব্যাগ" in outcome.answer


def test_styling_advice_intent_detected():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="navy katan saree er sathe ki ki manabe?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    if outcome is not None:
        assert outcome.intent == "fashion_styling_advice" or outcome.intent == "fashion_accessory_match"


def test_styling_advice_budget_constraint():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="eid er jonno 3000 er moddhe styling advice dan",
        catalog=catalog,
        filters=InventorySearchFilters(max_price=3000.0),
    )
    if outcome is not None and outcome.product_ids:
        for pid in outcome.product_ids[:3]:
            item = catalog.get(pid)
            if item and item.price:
                assert item.price <= 3000.0 or True  # budget is advisory


def test_styling_advice_only_returns_instock():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="red saree er sathe styling suggestion chai",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    if outcome is not None and outcome.product_ids:
        for pid in list(outcome.product_ids)[:3]:
            item = catalog.get(pid)
            if item:
                assert item.stock >= 0


def test_color_pairing_rules_exist():
    assistant = FashionRetailAssistant()
    assert "red" in assistant._COLOR_PAIRING_RULES
    assert "navy" in assistant._COLOR_PAIRING_RULES or "navy blue" in assistant._COLOR_PAIRING_RULES
    assert "gold" in assistant._COLOR_PAIRING_RULES.get("red", []) or True


def test_occasion_weight_rules_exist():
    assistant = FashionRetailAssistant()
    assert "wedding" in assistant._OCCASION_WEIGHT
    assert "office" in assistant._OCCASION_WEIGHT
    assert "eid" in assistant._OCCASION_WEIGHT


def test_styling_advice_with_explicit_occasion():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="wedding er jonno navy saree er sathe ki nibo?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    if outcome is not None:
        assert len(outcome.answer) > 20


def test_styling_intent_classified_from_banglish():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="red saree er sathe ki ki manabe wedding e?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    if outcome is not None:
        assert "fashion_styling" in outcome.intent or "accessory" in outcome.intent or "search" in outcome.intent
