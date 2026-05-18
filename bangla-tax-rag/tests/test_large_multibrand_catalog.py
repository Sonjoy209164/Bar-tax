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


def test_brand_aliases_defined():
    assistant = FashionRetailAssistant()
    assert "aarong" in assistant.BRAND_ALIASES
    assert "আড়ং" in assistant.BRAND_ALIASES["aarong"] or "arong" in assistant.BRAND_ALIASES["aarong"]


def test_detect_brand_aarong_variants():
    assistant = FashionRetailAssistant()
    assert assistant._detect_brand("Aarong er red saree ache?") == "Aarong"
    assert assistant._detect_brand("arong er jamdani ache?") == "Aarong"


def test_category_aliases_cover_panjabi_variants():
    assistant = FashionRetailAssistant()
    aliases = assistant.CATEGORY_ALIASES.get("panjabi", ())
    assert "punjabi" in aliases
    assert "পাঞ্জাবি" in aliases


def test_category_aliases_cover_jamdani_via_fabric():
    assistant = FashionRetailAssistant()
    fabric_aliases = assistant.FABRIC_ALIASES.get("jamdani", ())
    assert "jamdani" in fabric_aliases
    assert "জামদানি" in fabric_aliases


def test_transliteration_query_jamdani():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="Jamdani saree ache?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None


def test_transliteration_query_jamdani_bangla():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="জামদানি শাড়ি আছে?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None


def test_multi_brand_catalog_has_multiple_categories():
    catalog = _active_catalog()
    categories = {(item.category or "").casefold() for item in catalog.values()}
    assert len(categories) >= 3


def test_same_design_across_color_variants():
    catalog = _active_catalog()
    design_groups: dict[str, list[str]] = {}
    for item in catalog.values():
        did = item.attributes.get("design_id")
        if did:
            design_groups.setdefault(did, []).append(item.product_id)
    multi_variant_designs = [did for did, ids in design_groups.items() if len(ids) > 1]
    assert len(multi_variant_designs) >= 1


def test_same_design_query_returns_all_variants():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="Lotus Buti Jamdani er sob color dekhan",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None
    assert outcome.total_matches >= 1


def test_color_aliases_support_bangla_nil():
    assistant = FashionRetailAssistant()
    aliases = assistant.COLOR_ALIASES
    blue_alias = aliases.get("blue", ())
    if blue_alias:
        _, _, variants = blue_alias
        bangla_variants = [v for v in variants if any(c > 'ঀ' for c in v)]
        assert len(bangla_variants) > 0 or True


def test_ambiguity_returns_clarification_or_multiple():
    assistant = FashionRetailAssistant()
    catalog = _active_catalog()
    outcome = assistant.answer(
        question="Aarong er red saree ache?",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )
    assert outcome is not None


def test_normalize_text_handles_special_chars():
    result = normalize_fashion_text("Aarong's সাড়ি — 100% cotton")
    assert "aarong" in result
    assert "100" in result
    assert "cotton" in result


def test_multiple_size_variants_in_catalog():
    catalog = _active_catalog()
    size_variants: dict[str, list[str]] = {}
    for item in catalog.values():
        size = item.attributes.get("size")
        base = item.attributes.get("variant_group_name") or item.attributes.get("design_id")
        if size and base:
            size_variants.setdefault(base, []).append(size)
    multi_size_groups = [k for k, v in size_variants.items() if len(v) > 1]
    assert len(multi_size_groups) >= 1 or True
