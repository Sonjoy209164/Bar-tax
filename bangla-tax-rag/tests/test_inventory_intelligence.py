from types import SimpleNamespace

from app.core.schemas import InventorySearchFilters
from app.inventory import EcommerceReranker, InventoryIntentClassifier, InventoryPreferenceExtractor, ProductOntology


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


def test_ecommerce_reranker_prefers_exact_product_type_over_generic_semantic_match() -> None:
    ontology = ProductOntology()
    reranker = EcommerceReranker(ontology)
    extractor = InventoryPreferenceExtractor(ontology)
    preferences = extractor.extract("Find wireless headphones under 300 for office calls")

    headphones = SimpleNamespace(
        product_id="hp",
        name="Auralite Flex ANC Headphones",
        category="Audio",
        brand="Auralite",
        price=249.0,
        stock=18,
        tags=["audio", "wireless", "headphones"],
        snippet="Wireless noise-cancelling headphones under 300 for focused office work",
        attributes={"connectivity": "Bluetooth 5.3", "battery_hours": "35"},
        metadata={},
    )
    keyboard = SimpleNamespace(
        product_id="kb",
        name="KeyForge Wireless Mechanical Keyboard",
        category="Computing",
        brand="KeyForge",
        price=139.0,
        stock=17,
        tags=["computing", "wireless", "premium"],
        snippet="Wireless mechanical keyboard with tactile switches",
        attributes={},
        metadata={},
    )

    headphone_score = reranker.score_product(
        headphones,
        preferences=preferences,
        semantic_score=0.6,
        lexical_score=0.9,
    )
    keyboard_score = reranker.score_product(
        keyboard,
        preferences=preferences,
        semantic_score=0.9,
        lexical_score=0.5,
    )

    assert headphone_score.final_score > keyboard_score.final_score
    assert headphone_score.product_type_match == 1.0
    assert keyboard_score.unrelated_category_penalty > 0


def test_ecommerce_reranker_scores_budget_and_stock_fit() -> None:
    reranker = EcommerceReranker()
    preferences = InventoryPreferenceExtractor().extract("Need a budget laptop under 900 available now")
    in_budget = SimpleNamespace(
        product_id="value",
        name="Nimbus 13 Essential Laptop",
        category="Computing",
        brand="Nimbus",
        price=799.0,
        stock=16,
        tags=["computing", "laptop"],
        snippet="Lower-cost business laptop for everyday work",
        attributes={},
        metadata={},
    )
    out_of_stock = SimpleNamespace(
        product_id="premium",
        name="Nimbus 14 Business Ultrabook",
        category="Computing",
        brand="Nimbus",
        price=1199.0,
        stock=0,
        tags=["computing", "laptop", "premium"],
        snippet="Lightweight premium laptop",
        attributes={},
        metadata={},
    )

    in_budget_score = reranker.score_product(in_budget, preferences=preferences, semantic_score=0.8, lexical_score=0.8)
    out_of_stock_score = reranker.score_product(
        out_of_stock,
        preferences=preferences,
        semantic_score=0.8,
        lexical_score=0.8,
        assistant_mode="sales",
    )

    assert in_budget_score.final_score > out_of_stock_score.final_score
    assert in_budget_score.price_fit == 1.0
    assert out_of_stock_score.out_of_stock_penalty > 0
