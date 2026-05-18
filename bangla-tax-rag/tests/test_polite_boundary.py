from app.inventory.polite_boundary import classify_polite_boundary


def test_romantic_boundary_redirects_to_shopping() -> None:
    decision = classify_polite_boundary("amar ekta gf lagbe")

    assert decision is not None
    assert decision.boundary_type == "romantic_off_topic"
    assert decision.risk_level == "low"
    assert decision.allowed_action == "playful_redirect"
    assert "Girlfriend" in decision.answer
    assert "perfume" in decision.answer
    assert decision.follow_up_question
    assert "gift" in decision.recommended_categories


def test_date_request_is_romantic_boundary_not_occasion() -> None:
    decision = classify_polite_boundary("will you date me?")

    assert decision is not None
    assert decision.boundary_type == "romantic_off_topic"
    assert decision.allowed_action == "playful_redirect"


def test_impression_request_becomes_hidden_shopping_intent() -> None:
    decision = classify_polite_boundary("ami crush ke impress korte chai")

    assert decision is not None
    assert decision.boundary_type == "impression_shopping"
    assert decision.allowed_action == "ask_clarifying_question"
    assert "perfume" in decision.recommended_categories
    assert "Budget" in (decision.follow_up_question or "")


def test_wedding_without_product_becomes_event_need() -> None:
    decision = classify_polite_boundary("amar ekta biyete jaowa dorkar")

    assert decision is not None
    assert decision.boundary_type == "occasion_wedding"
    assert decision.risk_level == "low"
    assert decision.allowed_action == "occasion_recommendation"
    assert decision.slots["occasion"] == "wedding"
    assert "wedding" in decision.answer.casefold()
    assert "saree" in decision.recommended_categories


def test_gift_for_relationship_is_not_treated_as_joke() -> None:
    decision = classify_polite_boundary("gf er jonno birthday gift chai")

    assert decision is not None
    assert decision.boundary_type == "gift_recommendation"
    assert decision.slots["recipient"] == "girlfriend"
    assert "Budget" in (decision.follow_up_question or "")


def test_emotional_safe_message_gets_empathy_and_redirect() -> None:
    decision = classify_polite_boundary("amar mon kharap")

    assert decision is not None
    assert decision.boundary_type == "emotional_low_mood"
    assert decision.risk_level == "medium"
    assert "Sorry" in decision.answer
    assert "self-care" in decision.answer


def test_concrete_shopping_query_not_stolen_by_boundary_layer() -> None:
    decision = classify_polite_boundary("amar biyete porar jonno saree under 5000 dekhan")

    assert decision is None


def test_product_date_query_not_stolen_by_romantic_or_occasion_layer() -> None:
    decision = classify_polite_boundary("date er jonno perfume ache?")

    assert decision is None


def test_order_support_query_not_stolen_by_boundary_layer() -> None:
    decision = classify_polite_boundary("Dhaka delivery charge koto?")

    assert decision is None


def test_business_owner_query_not_stolen_by_boundary_layer() -> None:
    decision = classify_polite_boundary("which products should I restock?")

    assert decision is None


def test_bangla_event_reply_uses_bangla() -> None:
    decision = classify_polite_boundary("আমার একটা বিয়েতে যাওয়া দরকার")

    assert decision is not None
    assert decision.boundary_type == "occasion_wedding"
    assert decision.language == "bangla"
    assert "বিয়ে" in decision.answer or "বিয়ে" in decision.answer


def test_medical_advice_is_guarded_without_selling() -> None:
    decision = classify_polite_boundary("amar rash er jonno kon medicine khabo?")

    assert decision is not None
    assert decision.boundary_type == "medical_or_health_advice"
    assert decision.risk_level == "high"
    assert decision.allowed_action == "safe_refusal_redirect"
    assert decision.handoff_recommended is True
    assert "Medical advice" in decision.answer


def test_product_wellness_query_can_continue_to_inventory() -> None:
    decision = classify_polite_boundary("oily skin er jonno sunscreen ache?")

    assert decision is None


def test_legal_advice_is_guarded() -> None:
    decision = classify_polite_boundary("case korle ki hobe legal advice dao")

    assert decision is not None
    assert decision.boundary_type == "legal_advice"
    assert decision.risk_level == "high"
    assert decision.handoff_recommended is True


def test_political_topic_is_neutral_redirect() -> None:
    decision = classify_polite_boundary("election e kake vote dibo?")

    assert decision is not None
    assert decision.boundary_type == "political"
    assert decision.allowed_action == "safe_refusal_redirect"
    assert "neutral" in decision.answer.casefold()


def test_self_harm_disables_commerce_redirect() -> None:
    decision = classify_polite_boundary("ami more jabo")

    assert decision is not None
    assert decision.boundary_type == "self_harm_or_crisis"
    assert decision.risk_level == "critical"
    assert decision.allowed_action == "crisis_safe_response"
    assert not decision.recommended_categories
    assert decision.follow_up_question is None


def test_vague_shopping_asks_commercial_clarifier() -> None:
    decision = classify_polite_boundary("valo kichu dekhan")

    assert decision is not None
    assert decision.boundary_type == "vague_shopping"
    assert decision.allowed_action == "ask_clarifying_question"


def test_common_casual_question_gets_short_redirect() -> None:
    decision = classify_polite_boundary("tumi ki khaiso?")

    assert decision is not None
    assert decision.boundary_type == "joke_chitchat"
    assert decision.allowed_action == "short_humor_then_redirect"


def test_personal_bot_question_gets_role_boundary() -> None:
    decision = classify_polite_boundary("tomar boyosh koto?")

    assert decision is not None
    assert decision.boundary_type == "personal_question_about_bot"
    assert "shopping assistant" in decision.answer.casefold()


def test_order_tracking_and_payment_are_handled_without_dead_fallback() -> None:
    order = classify_polite_boundary("amar order track korte chai")
    payment = classify_polite_boundary("COD payment available?")

    assert order is not None
    assert order.boundary_type == "order_tracking_support"
    assert payment is not None
    assert payment.boundary_type == "payment_support"


def test_new_job_is_commercial_occasion() -> None:
    decision = classify_polite_boundary("new job join korbo, smart look chai")

    assert decision is not None
    assert decision.boundary_type == "occasion_new_job"
    assert decision.allowed_action == "occasion_recommendation"


def test_expanded_sensitive_and_abuse_phrases_are_guarded() -> None:
    legal = classify_polite_boundary("contract ta legal naki?")
    abuse = classify_polite_boundary("boka bot")

    assert legal is not None
    assert legal.boundary_type == "legal_advice"
    assert abuse is not None
    assert abuse.boundary_type == "abusive_mild"
