from app.inventory.polite_boundary import classify_polite_boundary


def test_romantic_boundary_redirects_to_shopping() -> None:
    decision = classify_polite_boundary("amar ekta gf lagbe")

    assert decision is not None
    assert decision.boundary_type == "romantic_boundary"
    assert "Girlfriend" in decision.answer
    assert "perfume" in decision.answer
    assert decision.follow_up_question
    assert "gift" in decision.recommended_categories


def test_wedding_without_product_becomes_event_need() -> None:
    decision = classify_polite_boundary("amar ekta biyete jaowa dorkar")

    assert decision is not None
    assert decision.boundary_type == "event_need"
    assert decision.slots["occasion"] == "wedding"
    assert "wedding" in decision.answer.casefold()
    assert "saree" in decision.recommended_categories


def test_gift_for_relationship_is_not_treated_as_joke() -> None:
    decision = classify_polite_boundary("gf er jonno birthday gift chai")

    assert decision is not None
    assert decision.boundary_type == "gift_need"
    assert decision.slots["recipient"] == "girlfriend"
    assert "Budget" in (decision.follow_up_question or "")


def test_emotional_safe_message_gets_empathy_and_redirect() -> None:
    decision = classify_polite_boundary("amar mon kharap")

    assert decision is not None
    assert decision.boundary_type == "emotional_need"
    assert "Sorry" in decision.answer
    assert "self-care" in decision.answer


def test_concrete_shopping_query_not_stolen_by_boundary_layer() -> None:
    decision = classify_polite_boundary("amar biyete porar jonno saree under 5000 dekhan")

    assert decision is None


def test_bangla_event_reply_uses_bangla() -> None:
    decision = classify_polite_boundary("আমার একটা বিয়েতে যাওয়া দরকার")

    assert decision is not None
    assert decision.boundary_type == "event_need"
    assert decision.language == "bangla"
    assert "বিয়ে" in decision.answer or "বিয়ে" in decision.answer
