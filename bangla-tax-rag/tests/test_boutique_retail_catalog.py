from pathlib import Path

from app.core.schemas import InventoryItemRecord, InventorySearchFilters
from app.inventory.fashion_retail import FashionRetailAssistant


ACTIVE_CATALOG_PATH = Path("data/inventory/catalog.jsonl")
BOUTIQUE_REFERENCE_CATALOG_PATH = Path("data/inventory/backups/catalog_before_hf_demo_20260514_121130.jsonl")


def _catalog_from(path: Path) -> dict[str, InventoryItemRecord]:
    items: dict[str, InventoryItemRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = InventoryItemRecord.model_validate_json(line)
        items[item.product_id] = item
    return items


def _active_catalog() -> dict[str, InventoryItemRecord]:
    return _catalog_from(ACTIVE_CATALOG_PATH)


def _boutique_reference_catalog() -> dict[str, InventoryItemRecord]:
    return _catalog_from(BOUTIQUE_REFERENCE_CATALOG_PATH)


def test_active_catalog_is_image_demo_inventory() -> None:
    catalog = _active_catalog()

    assert len(catalog) == 100
    assert {item.currency for item in catalog.values()} == {"BDT"}
    assert not any(item.category in {"Audio", "Computing", "Office"} for item in catalog.values())
    assert all(item.images for item in catalog.values())
    assert all((item.images[0].local_path or "").startswith("frontend/assets/demo_catalog/") for item in catalog.values())


def test_reference_boutique_catalog_is_clean_boutique_inventory() -> None:
    catalog = _boutique_reference_catalog()

    assert len(catalog) == 47
    assert {item.currency for item in catalog.values()} == {"BDT"}
    assert not any(item.category in {"Audio", "Computing", "Office"} for item in catalog.values())


def test_boutique_bot_answers_oily_skin_sunscreen_budget_query() -> None:
    outcome = FashionRetailAssistant().answer(
        question="Do you have oily skin sunscreen under 1000?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_search"
    assert outcome.product_ids[0] == "beauty-sunscreen-oily-spf50"
    assert "BDT 950" in outcome.answer


def test_boutique_bot_answers_banglish_mens_shoe_size() -> None:
    outcome = FashionRetailAssistant().answer(
        question="men er brown loafer size 42 ache?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_size_availability"
    assert outcome.product_ids[0] == "shoe-men-loafer-brown-42"
    assert "3 stock e ache" in outcome.answer


def test_boutique_bot_does_not_overmatch_other_size_variants() -> None:
    outcome = FashionRetailAssistant().answer(
        question="white panjabi L available?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_size_availability"
    assert outcome.product_ids[0] == "panjabi-cotton-white-l"
    assert "Size L" in outcome.answer
    assert "Size M is available in size L" not in outcome.answer


def test_boutique_bot_answers_direct_watch_query_as_search_not_matching() -> None:
    outcome = FashionRetailAssistant().answer(
        question="ladies rose gold watch ache?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_search"
    assert outcome.product_ids[0] == "watch-ladies-rose-gold"
    assert not outcome.cross_sell_product_ids


def test_boutique_bot_reports_out_of_stock_three_piece_variant() -> None:
    outcome = FashionRetailAssistant().answer(
        question="blue floral three piece M available?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_size_availability"
    assert outcome.product_ids[0] == "threepiece-floral-georgette-blue-m"
    assert "out of stock" in outcome.answer.casefold()
    assert "threepiece-floral-georgette-pink-m" in outcome.product_ids


def test_boutique_bot_answers_bangla_matching_bag_for_saree() -> None:
    outcome = FashionRetailAssistant().answer(
        question="নেভি কাতান শাড়ির সাথে কোন ব্যাগ মানাবে?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_accessory_match"
    assert outcome.slots.language == "bangla"
    assert "bag-potli-gold-beaded" in outcome.cross_sell_product_ids
    assert "bag-clutch-antique-gold" in outcome.cross_sell_product_ids
    assert not any(product_id.startswith("jewelry-") for product_id in outcome.cross_sell_product_ids)


def test_boutique_bot_keeps_same_design_context_for_followup() -> None:
    outcome = FashionRetailAssistant().answer(
        question="ei same design ta green color e ache?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
        focused_product_ids=("saree-jmd-lotus-red",),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_variant_color"
    assert outcome.product_ids[0] == "saree-jmd-lotus-green"
    assert "stock e nei" in outcome.answer.casefold()


def test_boutique_bot_answers_banglish_wedding_saree_request() -> None:
    outcome = FashionRetailAssistant().answer(
        question="amar biye kichu saree dekhan",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_search"
    assert outcome.product_ids
    assert outcome.slots.category_key == "saree"
    assert outcome.slots.occasion == "wedding"
    assert any(product_id.startswith("saree-ktn") or product_id.startswith("saree-jmd") for product_id in outcome.product_ids)


def test_boutique_bot_relaxes_eid_budget_saree_without_abstaining() -> None:
    outcome = FashionRetailAssistant().answer(
        question="eid er jonno 5000 er moddhe elegant saree",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_search"
    assert not outcome.abstained
    assert outcome.product_ids
    catalog = _boutique_reference_catalog()
    assert all(catalog[product_id].price <= 5000 for product_id in outcome.product_ids)
    assert all(catalog[product_id].attributes.get("category_key") == "saree" for product_id in outcome.product_ids)


def test_boutique_bot_does_not_let_old_saree_context_override_new_bag_query() -> None:
    outcome = FashionRetailAssistant().answer(
        question="amar office ache amake kichu bag dekhan",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
        conversation_history=[
            ("user", "amar biye kichu saree dekhan"),
            ("assistant", "Here are some wedding sarees."),
        ],
        focused_product_ids=("saree-ktn-meena-maroon",),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_search"
    assert outcome.slots.category_key == "bag"
    assert outcome.product_ids[0] == "bag-tote-black-everyday"
    catalog = _boutique_reference_catalog()
    assert all(catalog[product_id].attributes.get("category_key") == "bag" for product_id in outcome.product_ids)


def test_boutique_bot_enforces_men_filter_for_watch_or_perfume_compare() -> None:
    outcome = FashionRetailAssistant().answer(
        question="3000 taka er moddhe men watch ba perfume ache?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_compare"
    assert "watch-men-leather-brown" in outcome.product_ids
    assert "perfume-unisex-citrus-50ml" in outcome.product_ids
    assert "watch-ladies" not in " ".join(outcome.product_ids)
    assert "perfume-women" not in " ".join(outcome.product_ids)


def test_boutique_bot_routes_bag_and_bangle_matching_to_accessory_engine() -> None:
    outcome = FashionRetailAssistant().answer(
        question="maroon bridal katan er sathe kon bag ar bangle match korbe?",
        catalog=_boutique_reference_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_accessory_match"
    assert "jewelry-bangles-gold-meena" in outcome.cross_sell_product_ids
    assert "bag-clutch-antique-gold" in outcome.cross_sell_product_ids
    assert "bag-tote-black-everyday" not in outcome.cross_sell_product_ids[:2]
