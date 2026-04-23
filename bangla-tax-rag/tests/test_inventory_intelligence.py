from types import SimpleNamespace

from app.core.schemas import (
    InventoryAnswerPlan,
    InventoryBusinessSignalRecord,
    InventoryItemRecord,
    InventorySearchFilters,
    InventorySearchHit,
)
from app.inventory import (
    EcommerceReranker,
    InventoryAnswerPlanner,
    InventoryDecisionScorer,
    InventoryEvidenceContractBuilder,
    InventoryFinalAnswerVerifier,
    InventoryIntentClassifier,
    InventoryMemoryResolver,
    InventoryPreferenceExtractor,
    InventoryTradeoffReasoner,
    ProductOntology,
)


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


def test_product_ontology_prefers_accessory_type_for_laptop_bag_bundle_items() -> None:
    ontology = ProductOntology()
    laptop = SimpleNamespace(
        product_id="laptop",
        name="Nimbus 14 Business Ultrabook",
        category="Computing",
        tags=["computing", "laptop"],
        snippet="Lightweight 14 inch laptop",
        attributes={},
        metadata={},
    )
    bag = SimpleNamespace(
        product_id="bag",
        name="CarryShield Laptop Bag",
        category="Accessories",
        tags=["bag", "accessory"],
        snippet="Protective laptop bag for daily carry",
        attributes={},
        metadata={},
    )

    assert ontology.detect_product_type(product=bag) == "bag"
    assert ontology.valid_cross_sell(laptop, bag, explicit_cross_sell=True) is True


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


def test_inventory_decision_scorer_prefers_premium_recommendation_over_hit_order() -> None:
    scorer = InventoryDecisionScorer()
    budget = InventorySearchHit(
        product_id="budget",
        sku="CMP-LAP-001",
        name="Nimbus 14 Essential",
        category="Computing",
        brand="Nimbus",
        price=899.0,
        currency="USD",
        stock=16,
        tags=["computing", "laptop"],
        snippet="Lower-cost business laptop",
        evidence_scores={
            "final_score": 0.78,
            "product_type_match": 1.0,
            "price_fit": 0.82,
            "budget_fit": 0.95,
            "premium_fit": 0.0,
            "stock_fit": 1.0,
        },
        score=0.78,
    )
    premium = InventorySearchHit(
        product_id="premium",
        sku="CMP-LAP-002",
        name="Nimbus 14 Elite",
        category="Computing",
        brand="Nimbus",
        price=1799.0,
        currency="USD",
        stock=11,
        tags=["computing", "laptop", "premium"],
        snippet="Premium laptop with OLED display",
        evidence_scores={
            "final_score": 0.75,
            "product_type_match": 1.0,
            "price_fit": 0.65,
            "budget_fit": 0.2,
            "premium_fit": 1.0,
            "stock_fit": 1.0,
            "structured_spec_match": 0.8,
        },
        score=0.75,
    )

    ranked = scorer.rank_recommendations(hits=[budget, premium], sales_style="premium")

    assert ranked[0].product_id == "premium"
    assert ranked[0].evidence_scores["deterministic_recommendation_score"] > ranked[1].evidence_scores[
        "deterministic_recommendation_score"
    ]


def test_inventory_answer_planner_builds_rich_decision_metadata() -> None:
    ontology = ProductOntology()
    preferences = InventoryPreferenceExtractor(ontology).extract(
        "Need premium wireless headphones under 300 for office calls"
    )
    intent = InventoryIntentClassifier(ontology).classify(
        "Need premium wireless headphones under 300 for office calls"
    )
    contract_builder = InventoryEvidenceContractBuilder(ontology)
    planner = InventoryAnswerPlanner(ontology)
    primary = InventorySearchHit(
        product_id="prod-headphones",
        sku="AUD-HP-001",
        name="Auralite Flex ANC Headphones",
        category="Audio",
        brand="Auralite",
        price=249.0,
        currency="USD",
        stock=18,
        status="Active",
        tags=["audio", "wireless", "headphones", "premium"],
        snippet="Wireless noise-cancelling headphones under 300 for focused office work",
        attributes={"battery_hours": "35"},
        evidence_scores={
            "final_score": 0.82,
            "semantic_score": 0.7,
            "lexical_score": 0.95,
            "product_type_match": 1.0,
            "family_match": 1.0,
            "price_fit": 1.0,
            "stock_fit": 1.0,
            "metadata_match": 1.0,
            "reasons": ["exact product type match: headphones", "price is inside requested budget", "in stock"],
        },
        score=0.82,
    )
    alternative = InventorySearchHit(
        product_id="prod-earbuds",
        sku="AUD-EB-002",
        name="EchoWave Studio Earbuds",
        category="Audio",
        brand="EchoWave",
        price=129.0,
        currency="USD",
        stock=12,
        status="Active",
        tags=["audio", "wireless", "earbuds"],
        snippet="Compact wireless earbuds for calls",
        evidence_scores={
            "final_score": 0.58,
            "family_match": 1.0,
            "price_fit": 1.0,
            "stock_fit": 1.0,
            "reasons": ["same product family: audio_listening", "price is inside requested budget"],
        },
        score=0.58,
    )
    plan = InventoryAnswerPlan(
        intent="sales_premium",
        primary_product_id=primary.product_id,
        alternative_product_ids=[alternative.product_id],
    )
    evidence_contract = contract_builder.build(
        question="Need premium wireless headphones under 300 for office calls",
        answer_plan=plan,
        hits=[primary, alternative],
        preferences=preferences,
        business_signals={},
        next_best_question=None,
    )

    rich_plan = planner.enrich_plan(
        answer_plan=plan,
        evidence_contract=evidence_contract,
        intent_result=intent,
        preferences=preferences,
        strategy="sales_premium",
        next_best_question=None,
    )

    assert rich_plan.primary_reason is not None
    assert "Auralite Flex ANC Headphones" in rich_plan.primary_reason
    assert rich_plan.alternative_reason is not None
    assert "EchoWave Studio Earbuds" in rich_plan.alternative_reason
    assert rich_plan.tradeoffs
    assert rich_plan.next_best_question is not None
    assert rich_plan.confidence_breakdown["primary"]["final_score"] == 0.82
    assert rich_plan.confidence_breakdown["decision"]["strategy"] == "recommendation"
    assert rich_plan.evidence_contract is not None
    assert rich_plan.evidence_contract.required_tradeoffs


def test_inventory_answer_planner_explains_deterministic_comparison_scores() -> None:
    ontology = ProductOntology()
    builder = InventoryEvidenceContractBuilder(ontology)
    planner = InventoryAnswerPlanner(ontology)
    intent = InventoryIntentClassifier(ontology).classify("Compare these laptops")
    preferences = InventoryPreferenceExtractor(ontology).extract("Compare these laptops")
    primary = InventorySearchHit(
        product_id="pro",
        sku="CMP-LAP-100",
        name="CreatorCraft 16 Pro",
        category="Computing",
        brand="CreatorCraft",
        price=1699.0,
        currency="USD",
        stock=5,
        tags=["computing", "laptop"],
        snippet="Creator laptop with dedicated graphics",
        attributes={"ram": "32GB"},
        evidence_scores={
            "final_score": 0.81,
            "product_type_match": 1.0,
            "family_match": 1.0,
            "structured_spec_match": 0.8,
            "deterministic_comparison_score": 0.84,
            "deterministic_comparison_reasons": [
                "it is an exact comparison-fit product for the requested type",
                "price, stock, and core facts are all available for comparison",
            ],
        },
        score=0.81,
    )
    alternative = InventorySearchHit(
        product_id="air",
        sku="CMP-LAP-101",
        name="CreatorCraft 16 Air",
        category="Computing",
        brand="CreatorCraft",
        price=1499.0,
        currency="USD",
        stock=9,
        tags=["computing", "laptop"],
        snippet="Creator laptop with longer battery life",
        attributes={"ram": "16GB"},
        evidence_scores={
            "final_score": 0.75,
            "product_type_match": 1.0,
            "family_match": 1.0,
            "structured_spec_match": 0.65,
            "deterministic_comparison_score": 0.79,
            "deterministic_comparison_reasons": [
                "it is an exact comparison-fit product for the requested type",
                "enough core facts are present for a grounded comparison",
            ],
        },
        score=0.75,
    )
    plan = InventoryAnswerPlan(
        intent="comparison",
        primary_product_id=primary.product_id,
        alternative_product_ids=[alternative.product_id],
    )
    contract = builder.build(
        question="Compare these laptops",
        answer_plan=plan,
        hits=[primary, alternative],
        preferences=preferences,
        business_signals={},
        next_best_question=None,
    )

    rich_plan = planner.enrich_plan(
        answer_plan=plan,
        evidence_contract=contract,
        intent_result=intent,
        preferences=preferences,
        strategy="comparison",
        next_best_question=None,
    )

    assert "comparison scorecard" in (rich_plan.primary_reason or "").lower()
    assert "comparison scorecard" in (rich_plan.alternative_reason or "").lower()
    assert rich_plan.confidence_breakdown["decision"]["primary_score"] == 0.84


def test_inventory_evidence_contract_detects_stock_contradictions_and_missing_specs() -> None:
    ontology = ProductOntology()
    builder = InventoryEvidenceContractBuilder(ontology)
    preferences = InventoryPreferenceExtractor(ontology).extract("Recommend a laptop with 16GB RAM")
    hit = InventorySearchHit(
        product_id="prod-laptop",
        sku="CMP-LAP-001",
        name="Nimbus 14 Business Ultrabook",
        category="Computing",
        brand="Nimbus",
        price=None,
        currency="USD",
        stock=8,
        status="Active",
        tags=["computing", "laptop"],
        snippet="Lightweight business laptop",
        attributes={},
        metadata={},
        evidence_scores={"final_score": 0.67, "reasons": ["exact product type match: laptop"]},
        score=0.67,
    )
    plan = InventoryAnswerPlan(primary_product_id=hit.product_id)

    contract = builder.build(
        question="Recommend a laptop with 16GB RAM",
        answer_plan=plan,
        hits=[hit],
        preferences=preferences,
        business_signals={
            hit.product_id: InventoryBusinessSignalRecord(
                product_id=hit.product_id,
                inventory_on_hand=3,
                inventory_snapshot_at="2026-04-20T10:00:00Z",
            )
        },
        next_best_question=None,
    )

    assert contract.contradictions
    assert any("conflicting stock signals" in item.lower() for item in contract.contradictions)
    assert any("no listed price" in item.lower() for item in contract.missing_facts)
    assert any("missing structured specs" in item.lower() for item in contract.missing_facts)
    stock_fact = next(fact for fact in contract.candidate_evidence[0].facts if fact.key == "stock")
    assert stock_fact.status == "conflicting"


def test_inventory_evidence_contract_captures_business_restock_facts() -> None:
    ontology = ProductOntology()
    builder = InventoryEvidenceContractBuilder(ontology)
    preferences = InventoryPreferenceExtractor(ontology).extract("What should I restock first to prevent stockout?")
    hit = InventorySearchHit(
        product_id="prod-mic",
        sku="AUD-MIC-004",
        name="VoxCast USB Podcast Microphone",
        category="Audio",
        brand="VoxCast",
        price=159.0,
        currency="USD",
        stock=2,
        status="Low Stock",
        tags=["audio", "microphone"],
        snippet="Cardioid USB microphone for podcasts and webinars",
        evidence_scores={"final_score": 0.88, "reasons": ["in stock", "metadata/features match requested need"]},
        score=0.88,
    )
    plan = InventoryAnswerPlan(primary_product_id=hit.product_id)

    contract = builder.build(
        question="What should I restock first to prevent stockout?",
        answer_plan=plan,
        hits=[hit],
        preferences=preferences,
        business_signals={
            hit.product_id: InventoryBusinessSignalRecord(
                product_id=hit.product_id,
                units_sold=64,
                inventory_on_hand=2,
                supplier_lead_time_days=21,
                gross_margin_rate=0.33,
                demand_score=0.91,
                inventory_snapshot_at="2026-04-19T06:00:00Z",
            )
        },
        next_best_question="Do you want the next two restock candidates as well?",
    )

    allowed_claims = " ".join(contract.allowed_claims).lower()
    assert "demand score is 0.91" in allowed_claims
    assert "supplier lead time is 21 day(s)" in allowed_claims
    assert "margin rate is 33.0%" in allowed_claims
    assert contract.follow_up_question_rules


def test_inventory_decision_scorer_ranks_restock_candidates_by_operational_priority() -> None:
    scorer = InventoryDecisionScorer()
    candidates = [
        (
            InventorySearchHit(
                product_id="safe",
                sku="AUD-HP-001",
                name="Auralite Flex ANC Headphones",
                category="Audio",
                brand="Auralite",
                price=249.0,
                currency="USD",
                stock=1,
                tags=["audio", "headphones"],
                snippet="Wireless headphones",
                score=0.5,
            ),
            InventoryItemRecord(
                product_id="safe",
                sku="AUD-HP-001",
                name="Auralite Flex ANC Headphones",
                category="Audio",
                brand="Auralite",
                short_description="Wireless headphones",
                price=249.0,
                currency="USD",
                stock=1,
                status="Low Stock",
                tags=["audio", "headphones"],
                include_in_rag=True,
            ),
            InventoryBusinessSignalRecord(
                product_id="safe",
                units_sold=8,
                order_count=6,
                inventory_on_hand=1,
                supplier_lead_time_days=5,
                gross_margin_rate=0.12,
                demand_score=0.22,
            ),
        ),
        (
            InventorySearchHit(
                product_id="priority",
                sku="AUD-MIC-004",
                name="VoxCast USB Podcast Microphone",
                category="Audio",
                brand="VoxCast",
                price=159.0,
                currency="USD",
                stock=2,
                tags=["audio", "microphone"],
                snippet="USB microphone",
                score=0.5,
            ),
            InventoryItemRecord(
                product_id="priority",
                sku="AUD-MIC-004",
                name="VoxCast USB Podcast Microphone",
                category="Audio",
                brand="VoxCast",
                short_description="USB microphone",
                price=159.0,
                currency="USD",
                stock=2,
                status="Low Stock",
                tags=["audio", "microphone"],
                include_in_rag=True,
            ),
            InventoryBusinessSignalRecord(
                product_id="priority",
                units_sold=64,
                order_count=48,
                inventory_on_hand=2,
                supplier_lead_time_days=21,
                gross_margin_rate=0.33,
                supplier_risk_score=0.35,
                demand_score=0.91,
            ),
        ),
    ]

    ranked = scorer.rank_restock_candidates(candidates=candidates)

    assert ranked[0].product_id == "priority"
    assert ranked[0].evidence_scores["deterministic_restock_score"] > ranked[1].evidence_scores[
        "deterministic_restock_score"
    ]


def test_inventory_evidence_contract_is_complete_for_compare_flow() -> None:
    ontology = ProductOntology()
    builder = InventoryEvidenceContractBuilder(ontology)
    preferences = InventoryPreferenceExtractor(ontology).extract("Compare these wireless headphones")
    primary = InventorySearchHit(
        product_id="prod-headphones",
        sku="AUD-HP-001",
        name="Auralite Flex ANC Headphones",
        category="Audio",
        brand="Auralite",
        price=249.0,
        currency="USD",
        stock=18,
        status="Active",
        tags=["audio", "wireless", "headphones"],
        snippet="Wireless ANC headphones",
        evidence_scores={"final_score": 0.82, "reasons": ["exact product type match: headphones"]},
        score=0.82,
    )
    alternative = InventorySearchHit(
        product_id="prod-earbuds",
        sku="AUD-EB-002",
        name="EchoWave Studio Earbuds",
        category="Audio",
        brand="EchoWave",
        price=129.0,
        currency="USD",
        stock=12,
        status="Active",
        tags=["audio", "wireless", "earbuds"],
        snippet="Compact wireless earbuds",
        evidence_scores={"final_score": 0.58, "reasons": ["same product family: audio_listening"]},
        score=0.58,
    )
    rejected = InventorySearchHit(
        product_id="prod-speaker",
        sku="AUD-SPK-009",
        name="RoomBeam Speaker",
        category="Audio",
        brand="RoomBeam",
        price=199.0,
        currency="USD",
        stock=9,
        status="Active",
        tags=["audio", "speaker"],
        snippet="Conference speaker",
        evidence_scores={"final_score": 0.31, "reasons": ["penalized as unrelated or weakly related"]},
        score=0.31,
    )
    plan = InventoryAnswerPlan(
        primary_product_id=primary.product_id,
        alternative_product_ids=[alternative.product_id],
    )

    contract = builder.build(
        question="Compare these wireless headphones",
        answer_plan=plan,
        hits=[primary, alternative, rejected],
        preferences=preferences,
        business_signals={},
        next_best_question="Should I compare comfort, battery, or price next?",
    )

    assert contract.primary_candidate_ids == [primary.product_id, alternative.product_id]
    assert contract.rejected_candidate_ids == [rejected.product_id]
    assert len(contract.candidate_evidence) == 3
    assert any(candidate.role == "primary" for candidate in contract.candidate_evidence)
    assert any(candidate.role == "alternative" for candidate in contract.candidate_evidence)
    assert any(candidate.role == "rejected" for candidate in contract.candidate_evidence)


def test_inventory_tradeoff_reasoner_distinguishes_fallbacks_and_cross_sells() -> None:
    ontology = ProductOntology()
    preferences = InventoryPreferenceExtractor(ontology).extract(
        "Need premium wireless headphones under 300 for office calls"
    )
    reasoner = InventoryTradeoffReasoner(ontology)
    primary = InventorySearchHit(
        product_id="prod-headphones",
        sku="AUD-HP-001",
        name="Auralite Flex ANC Headphones",
        category="Audio",
        brand="Auralite",
        price=249.0,
        currency="USD",
        stock=4,
        status="Low Stock",
        tags=["audio", "wireless", "headphones", "premium"],
        snippet="Wireless noise-cancelling headphones under 300 for focused office work",
        score=0.82,
    )
    earbuds = InventorySearchHit(
        product_id="prod-earbuds",
        sku="AUD-EB-002",
        name="EchoWave Studio Earbuds",
        category="Audio",
        brand="EchoWave",
        price=129.0,
        currency="USD",
        stock=12,
        status="Active",
        tags=["audio", "wireless", "earbuds"],
        snippet="Compact wireless earbuds for calls",
        score=0.58,
    )
    microphone = InventorySearchHit(
        product_id="prod-mic",
        sku="AUD-MIC-003",
        name="VoxCast USB Podcast Microphone",
        category="Audio",
        brand="VoxCast",
        price=159.0,
        currency="USD",
        stock=8,
        status="Active",
        tags=["audio", "microphone"],
        snippet="USB microphone for meetings and webinars",
        score=0.5,
    )

    tradeoffs = reasoner.build_tradeoffs(
        primary=primary,
        alternatives=[earbuds],
        cross_sells=[microphone],
        preferences=preferences,
    )

    joined = " ".join(tradeoffs).lower()
    assert "not an equivalent over-ear headphone substitute" in joined
    assert "premium lead" in joined
    assert "limited stock" in joined or "safer availability" in joined
    assert "cross-sell add-on" in joined
    assert "not a substitute" in joined


def test_inventory_final_answer_verifier_catches_unsupported_price_and_claims() -> None:
    verifier = InventoryFinalAnswerVerifier()
    hit = InventorySearchHit(
        product_id="prod-watch",
        sku="ACC-WAT-001",
        name="TrailMark Smart Watch",
        category="Wearables",
        brand="TrailMark",
        price=199.0,
        currency="USD",
        stock=10,
        status="Active",
        tags=["watch", "wearable", "fitness"],
        snippet="Fitness watch with heart-rate and GPS tracking",
        score=0.7,
    )
    plan = InventoryAnswerPlan(primary_product_id=hit.product_id)

    verification = verifier.verify(
        answer="TrailMark Smart Watch is available for USD 999.00 with free shipping.",
        answer_plan=plan,
        hits=[hit],
    )

    assert verification.passed is False
    assert verification.checked_final_answer is True
    assert any("unsupported price" in issue.lower() for issue in verification.final_answer_issues)
    assert any("free shipping" in issue.lower() for issue in verification.final_answer_issues)


def test_inventory_final_answer_verifier_catches_cross_sell_as_substitute() -> None:
    verifier = InventoryFinalAnswerVerifier()
    laptop = InventorySearchHit(
        product_id="prod-laptop",
        sku="CMP-LAP-001",
        name="Nimbus 14 Business Ultrabook",
        category="Computing",
        brand="Nimbus",
        price=1199.0,
        currency="USD",
        stock=8,
        tags=["computing", "laptop"],
        snippet="Lightweight 14 inch laptop",
        score=0.8,
    )
    mouse = InventorySearchHit(
        product_id="prod-mouse",
        sku="CMP-MS-002",
        name="GlidePoint Wireless Mouse",
        category="Computing",
        brand="GlidePoint",
        price=49.0,
        currency="USD",
        stock=31,
        tags=["computing", "mouse"],
        snippet="Silent wireless mouse",
        score=0.5,
    )
    plan = InventoryAnswerPlan(
        primary_product_id=laptop.product_id,
        cross_sell_product_ids=[mouse.product_id],
    )

    verification = verifier.verify(
        answer="If they do not want the laptop, switch to GlidePoint Wireless Mouse as the replacement.",
        answer_plan=plan,
        hits=[laptop, mouse],
    )

    assert verification.passed is False
    assert any("cross-sell" in issue.lower() and "substitute" in issue.lower() for issue in verification.final_answer_issues)


def test_inventory_final_answer_verifier_uses_contract_supported_stock_values() -> None:
    ontology = ProductOntology()
    builder = InventoryEvidenceContractBuilder(ontology)
    verifier = InventoryFinalAnswerVerifier(ontology)
    preferences = InventoryPreferenceExtractor(ontology).extract("Tell me about this laptop")
    laptop = InventorySearchHit(
        product_id="prod-laptop",
        sku="CMP-LAP-001",
        name="Nimbus 14 Business Ultrabook",
        category="Computing",
        brand="Nimbus",
        price=1199.0,
        currency="USD",
        stock=8,
        tags=["computing", "laptop"],
        snippet="Lightweight 14 inch laptop",
        score=0.8,
    )
    plan = InventoryAnswerPlan(primary_product_id=laptop.product_id)
    contract = builder.build(
        question="Tell me about this laptop",
        answer_plan=plan,
        hits=[laptop],
        preferences=preferences,
        business_signals={
            laptop.product_id: InventoryBusinessSignalRecord(
                product_id=laptop.product_id,
                inventory_on_hand=3,
                inventory_snapshot_at="2026-04-20T10:00:00Z",
            )
        },
        next_best_question=None,
    )
    plan = plan.model_copy(update={"evidence_contract": contract})

    verification = verifier.verify(
        answer="Nimbus 14 Business Ultrabook has 3 units in stock right now.",
        answer_plan=plan,
        hits=[laptop],
    )

    assert verification.passed is True


def test_inventory_memory_resolver_uses_reference_but_ignores_new_explicit_request() -> None:
    resolver = InventoryMemoryResolver()
    last_plan = InventoryAnswerPlan(
        primary_product_id="prod-watch",
        alternative_product_ids=["prod-watch-value"],
    )

    resolved = resolver.resolve(
        question="Tell me more about the first one",
        filters=InventorySearchFilters(),
        focused_product_ids=["prod-watch", "prod-watch-value"],
        active_filters=InventorySearchFilters(categories=["Wearables"]),
        last_answer_plan=last_plan,
    )

    assert resolved.resolution.used_memory is True
    assert resolved.resolution.resolved_product_ids == ["prod-watch"]
    assert resolved.filters.product_ids == ["prod-watch"]
    assert resolved.filters.categories == ["Wearables"]

    ignored = resolver.resolve(
        question="Show me laptops",
        filters=InventorySearchFilters(),
        focused_product_ids=["prod-watch"],
        active_filters=InventorySearchFilters(categories=["Wearables"]),
        last_answer_plan=last_plan,
    )

    assert ignored.resolution.used_memory is False
    assert ignored.filters.product_ids == []
    assert ignored.filters.categories == []
    assert ignored.resolution.ignored_memory_reason is not None
