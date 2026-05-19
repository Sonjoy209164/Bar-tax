from pathlib import Path

from app.core.schemas import InventoryItemRecord, InventorySearchFilters
from app.inventory.fashion_retail import FashionRetailAssistant


def _sample_catalog() -> dict[str, InventoryItemRecord]:
    path = Path("data/inventory/saree_shop_catalog.jsonl")
    items: dict[str, InventoryItemRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = InventoryItemRecord.model_validate_json(line)
        items[item.product_id] = item
    return items


def test_fashion_retail_answers_same_design_color_variant() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="Do you have the Lotus Buti Jamdani in blue?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_variant_color"
    assert outcome.product_ids[0] == "saree-jmd-lotus-blue"
    assert "Yes" in outcome.answer
    assert "2 in stock" in outcome.answer


def test_fashion_retail_checks_same_design_color_stock_before_alternatives() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="I liked the red Lotus Buti Jamdani. Do you have the same design in green?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_variant_color"
    assert outcome.product_ids[0] == "saree-jmd-lotus-green"
    assert "out of stock" in outcome.answer.casefold()
    assert "red" in outcome.answer.casefold()
    assert "royal blue" in outcome.answer.casefold()


def test_fashion_retail_answers_exact_blouse_size_available() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="Is red blouse size 38 available?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_size_availability"
    assert outcome.product_ids[0] == "blouse-silk-princess-red-38"
    assert "Yes" in outcome.answer
    assert "2 in stock" in outcome.answer


def test_fashion_retail_answers_exact_blouse_size_out_of_stock() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="Is red blouse size 40 available?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_size_availability"
    assert outcome.product_ids[0] == "blouse-silk-princess-red-40"
    assert "out of stock" in outcome.answer.casefold()
    assert "Size 40" in outcome.answer


def test_fashion_retail_searches_fashion_slots_not_old_office_category() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="Show me a lightweight office saree under 4000 taka.",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_search"
    assert outcome.product_ids
    assert all(product_id.startswith(("saree-msn", "saree-cot")) for product_id in outcome.product_ids)
    assert "Pastel Soft Muslin Saree" in outcome.answer


def test_fashion_retail_treats_dress_as_dress_not_salwar_kameez() -> None:
    assistant = FashionRetailAssistant()
    catalog = {
        "dress-black-maxi": InventoryItemRecord(
            product_id="dress-black-maxi",
            sku="DRESS001",
            name="Black Georgette Maxi",
            category="Dress",
            price=2500,
            stock=1,
            status="active",
            attributes={
                "category_key": "dress",
                "color": "Black",
                "color_family": "black",
                "garment_type": "maxi",
            },
            tags=["Dress", "Black", "Georgette"],
        ),
        "salwar-black": InventoryItemRecord(
            product_id="salwar-black",
            sku="SALWAR001",
            name="Black Salwar Kameez",
            category="Salwar Kameez",
            price=2200,
            stock=1,
            status="active",
            attributes={
                "category_key": "salwar_kameez",
                "color": "Black",
                "color_family": "black",
            },
            tags=["Salwar Kameez", "Black"],
        ),
    }

    outcome = assistant.answer(
        question="black dress under 3000",
        catalog=catalog,
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.slots.category_key == "dress"
    assert outcome.slots.category_label == "Dress"
    assert outcome.product_ids[0] == "dress-black-maxi"


def test_fashion_retail_exact_product_title_bypasses_clarification() -> None:
    assistant = FashionRetailAssistant()
    catalog = {
        "hooded-blue": InventoryItemRecord(
            product_id="hooded-blue",
            sku="MLHTS14055",
            name="Long Sleeve Hooded T-Shirt",
            category="T Shirt",
            price=1290,
            currency="BDT",
            stock=0,
            status="inactive",
            attributes={
                "category_key": "shirt",
                "color": "Blue",
                "color_family": "blue",
            },
            tags=["Long Sleeve Hooded T-Shirt", "T Shirt", "Blue"],
        ),
        "hooded-red": InventoryItemRecord(
            product_id="hooded-red",
            sku="MLHTS14057",
            name="Long Sleeve Hooded T-Shirt",
            category="T Shirt",
            price=1290,
            currency="BDT",
            stock=0,
            status="inactive",
            attributes={
                "category_key": "shirt",
                "color": "Red",
                "color_family": "red",
            },
            tags=["Long Sleeve Hooded T-Shirt", "T Shirt", "Red"],
        ),
        "generic-tshirt": InventoryItemRecord(
            product_id="generic-tshirt",
            sku="TSHIRT001",
            name="T-Shirt",
            category="T Shirt",
            price=700,
            currency="BDT",
            stock=5,
            status="active",
            attributes={"category_key": "shirt"},
            tags=["T Shirt"],
        ),
    }
    for index in range(20):
        product_id = f"generic-shirt-{index}"
        catalog[product_id] = InventoryItemRecord(
            product_id=product_id,
            sku=f"SHIRT{index:03d}",
            name=f"Everyday Shirt {index}",
            category="Shirt",
            price=1500 + index,
            currency="BDT",
            stock=3,
            status="active",
            attributes={"category_key": "shirt"},
            tags=["shirt"],
        )

    outcome = assistant.answer(
        question="Long Sleeve Hooded T-Shirt",
        catalog=catalog,
        filters=InventorySearchFilters(),
        allow_llm_slots=False,
    )

    assert outcome is not None
    assert outcome.intent == "fashion_search"
    assert outcome.follow_up_question is None
    assert outcome.product_ids == ("hooded-blue", "hooded-red")
    assert "generic-tshirt" not in outcome.product_ids
    assert "out of stock" in outcome.answer.casefold()
    assert "occasion" not in outcome.answer.casefold()
    assert "preferred color" not in outcome.answer.casefold()


def test_fashion_retail_exact_product_title_inside_phrase_returns_catalog_facts() -> None:
    assistant = FashionRetailAssistant()
    catalog = {
        "hooded-blue": InventoryItemRecord(
            product_id="hooded-blue",
            sku="MLHTS14055",
            name="Long Sleeve Hooded T-Shirt",
            category="T Shirt",
            price=1290,
            currency="BDT",
            stock=4,
            status="active",
            attributes={"category_key": "shirt", "color": "Blue", "color_family": "blue"},
            tags=["Long Sleeve Hooded T-Shirt", "T Shirt", "Blue"],
        ),
    }

    outcome = assistant.answer(
        question="do you have Long Sleeve Hooded T Shirt?",
        catalog=catalog,
        filters=InventorySearchFilters(),
        allow_llm_slots=False,
    )

    assert outcome is not None
    assert outcome.product_ids == ("hooded-blue",)
    assert "Yes" in outcome.answer
    assert "4 in stock" in outcome.answer
    assert outcome.follow_up_question is None


def test_fashion_retail_matches_accessories_by_compatibility_metadata() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="What accessories match the navy bridal katan saree?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_accessory_match"
    assert "acc-bangles-gold-meena" in outcome.cross_sell_product_ids
    assert "acc-clutch-antique-gold" in outcome.cross_sell_product_ids
    assert all(not product_id.startswith("acc-cablecraft") for product_id in outcome.product_ids)
    assert all(not product_id.startswith("blouse-") for product_id in outcome.product_ids)


def test_fashion_retail_does_not_intercept_non_fashion_questions() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="Need wireless headphones under 300 for office calls",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is None


def test_fashion_retail_understands_bangla_same_design_color_with_context() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="এই একই ডিজাইনটা নীল রঙে আছে?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
        focused_product_ids=("saree-jmd-lotus-red",),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_variant_color"
    assert outcome.slots.language == "bangla"
    assert outcome.product_ids[0] == "saree-jmd-lotus-blue"
    assert "জি" in outcome.answer
    assert "স্টকে" in outcome.answer


def test_fashion_retail_understands_banglish_same_design_color_with_context() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="ei same design ta green color e ache?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
        focused_product_ids=("saree-jmd-lotus-red",),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_variant_color"
    assert outcome.slots.language == "banglish"
    assert outcome.product_ids[0] == "saree-jmd-lotus-green"
    assert "stock e nei" in outcome.answer.casefold()


def test_fashion_retail_understands_bangla_size_with_bangla_digits() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="লাল ব্লাউজ সাইজ ৩৮ আছে?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_size_availability"
    assert outcome.slots.size == "38"
    assert outcome.product_ids[0] == "blouse-silk-princess-red-38"
    assert "স্টকে" in outcome.answer


def test_fashion_retail_understands_bangla_budget_and_occasion_search() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="৪০০০ টাকার মধ্যে অফিসে পরার হালকা শাড়ি দেখান",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_search"
    assert outcome.slots.budget_max == 4000.0
    assert outcome.slots.category_key == "saree"
    assert outcome.product_ids[:3] == (
        "saree-msn-pastel-peach",
        "saree-msn-pastel-mint",
        "saree-msn-pastel-lavender",
    )


def test_fashion_retail_understands_bangla_accessory_matching() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="নেভি ব্রাইডাল কাতান শাড়ির সাথে কোন গয়না বা ক্লাচ মানাবে?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is not None
    assert outcome.intent == "fashion_accessory_match"
    assert outcome.slots.language == "bangla"
    assert "acc-bangles-gold-meena" in outcome.cross_sell_product_ids
    assert "acc-clutch-antique-gold" in outcome.cross_sell_product_ids
    assert all(not product_id.startswith("acc-cablecraft") for product_id in outcome.product_ids)


def test_fashion_retail_does_not_intercept_banglish_non_fashion_question() -> None:
    assistant = FashionRetailAssistant()
    outcome = assistant.answer(
        question="office call er jonno wireless headphones ache?",
        catalog=_sample_catalog(),
        filters=InventorySearchFilters(),
    )

    assert outcome is None
