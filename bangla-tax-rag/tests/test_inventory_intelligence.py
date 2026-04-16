from types import SimpleNamespace

from app.core.schemas import InventorySearchFilters
from app.inventory import InventoryIntentClassifier, InventoryPreferenceExtractor, ProductOntology


def test_inventory_intent_classifier_detects_core_intents() -> None:
    classifier = InventoryIntentClassifier()

    assert classifier.classify("how are you").intent == "small_talk"
    assert classifier.classify("This is too expensive, what should I say?").intent == "price_objection"
    assert classifier.classify("Compare these two laptops").intent == "comparison"
    assert classifier.classify("What can I bundle with this laptop?").intent == "cross_sell"
    assert classifier.classify("Show me some watches").intent == "product_search"


def test_inventory_preference_extractor_reads_product_budget_and_use_case() -> None:
    extractor = InventoryPreferenceExtractor()

    profile = extractor.extract("Need premium wireless headphones under $300 for office calls")

    assert profile.product_type == "headphones"
    assert profile.product_family == "audio_listening"
    assert profile.category == "Audio"
    assert profile.budget_max == 300.0
    assert profile.quality_level == "premium"
    assert "wireless" in profile.feature_requirements
    assert "office_calls" in profile.use_cases
    assert profile.confidence > 0.5


def test_inventory_preference_extractor_uses_filters_and_brand_hints() -> None:
    extractor = InventoryPreferenceExtractor()
    products = [
        SimpleNamespace(brand="Auralite"),
        SimpleNamespace(brand="Nimbus"),
    ]

    profile = extractor.extract(
        "Find Auralite earbuds between 50 and 150",
        filters=InventorySearchFilters(product_ids=["prod-1"]),
        products=products,
    )

    assert profile.product_type == "earbuds"
    assert profile.brand == "Auralite"
    assert profile.budget_min == 50.0
    assert profile.budget_max == 150.0
    assert profile.selected_product_ids == ("prod-1",)


def test_product_ontology_rejects_unrelated_substitutes() -> None:
    ontology = ProductOntology()
    headphones = SimpleNamespace(
        product_id="hp",
        name="Auralite Flex ANC Headphones",
        category="Audio",
        tags=["audio", "headphones", "wireless"],
        snippet="Wireless noise-cancelling headphones",
        attributes={},
        metadata={},
    )
    earbuds = SimpleNamespace(
        product_id="eb",
        name="EchoWave Studio Earbuds",
        category="Audio",
        tags=["audio", "earbuds", "wireless"],
        snippet="Compact wireless earbuds",
        attributes={},
        metadata={},
    )
    keyboard = SimpleNamespace(
        product_id="kb",
        name="KeyForge Mechanical Keyboard",
        category="Computing",
        tags=["keyboard", "wireless"],
        snippet="Wireless mechanical keyboard",
        attributes={},
        metadata={},
    )

    assert ontology.detect_product_type(product=headphones) == "headphones"
    assert ontology.valid_alternative(headphones, earbuds) is True
    assert ontology.valid_alternative(headphones, keyboard) is False
    assert ontology.relation_score("headphones", headphones) == 3
    assert ontology.relation_score("headphones", keyboard) == 0
