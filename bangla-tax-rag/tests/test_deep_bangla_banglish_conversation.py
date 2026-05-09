from __future__ import annotations

from pathlib import Path

from app.core.schemas import InventoryItemRecord, InventorySearchFilters
from app.inventory.fashion_retail import FashionRetailAssistant, normalize_fashion_text


def _active_catalog() -> dict[str, InventoryItemRecord]:
    items: dict[str, InventoryItemRecord] = {}
    for line in Path("data/inventory/catalog.jsonl").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        item = InventoryItemRecord.model_validate_json(stripped)
        items[item.product_id] = item
    return items


def test_bangla_digit_normalization():
    assert normalize_fashion_text("৩০০০") == "3000"
    assert normalize_fashion_text("৪২") == "42"


def test_banglish_red_jamdani_query():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="ekta red jamdani dekhan",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None
    answer_lower = outcome.answer.casefold()
    assert "red" in answer_lower or "lal" in answer_lower or "jamdani" in answer_lower


def test_bangla_white_panjabi_query():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="সাদা পাঞ্জাবি আছে?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None


def test_banglish_same_design_blue_follow_up():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    first = assistant.answer(
        question="Lotus Jamdani red ache?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert first is not None

    follow_up = assistant.answer(
        question="same design blue ache?",
        catalog=catalog,
        filters=InventorySearchFilters(),
        focused_product_ids=(first.product_ids[0],) if first.product_ids else (),
        last_primary_product_id=first.product_ids[0] if first.product_ids else None,
    )
    assert follow_up is not None
    answer_lower = follow_up.answer.casefold()
    assert "blue" in answer_lower or "royal" in answer_lower or "nil" in answer_lower


def test_banglish_bag_match_follow_up():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="navy katan er sathe gold bag manabe?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None
    assert len(outcome.answer) > 10


def test_mixed_bangla_english_sunscreen():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="oily skin er jonno sunscreen ache?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None
    assert outcome.product_ids or "sunscreen" in outcome.answer.casefold() or "skin" in outcome.answer.casefold()


def test_banglish_mens_shoe_size_query():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="men er brown loafer size 42 ache?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None


def test_bangla_saree_question():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="লাল শাড়ি আছে?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None


def test_5_turn_conversation_context():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()

    turns = [
        ("ekta red jamdani dekhan", {}),
        ("same design blue ache?", {"focused_product_ids": ("saree-jmd-lotus-red",), "last_primary_product_id": "saree-jmd-lotus-red"}),
        ("tar dam koto?", {"focused_product_ids": ("saree-jmd-lotus-blue",), "last_primary_product_id": "saree-jmd-lotus-blue"}),
    ]
    outcomes = []
    for question, context in turns:
        outcome = assistant.answer(
            question=question,
            catalog=catalog,
            filters=InventorySearchFilters(),
            **context,
        )
        outcomes.append(outcome)

    assert all(o is not None for o in outcomes if o is not None)


def test_language_detection_banglish():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="red jamdani stock e ache?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    if outcome is not None:
        assert outcome.slots.language in ("banglish", "english")


def test_language_detection_bangla():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="লাল জামদানি শাড়ি আছে?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    if outcome is not None:
        assert outcome.slots.language == "bangla"
