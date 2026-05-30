from __future__ import annotations

from app.core.schemas import InventorySearchFilters
from app.inventory.conversation_flow import (
    decide_flow,
    filters_for_flow_continuation,
    is_slot_update,
)
from app.inventory.conversation_state import ConversationState
from app.inventory.ontology import ProductOntology


def _state(category_key: str = "salwar_kameez") -> ConversationState:
    return ConversationState(
        session_id="flow-salwar",
        last_shown_product_ids=["salwar-1", "salwar-2"],
        last_primary_product_id="salwar-1",
        active_slots={"category_key": category_key},
        last_intent="fashion_search",
        turn_count=1,
    )


def test_slot_only_color_occasion_continues_active_product_flow() -> None:
    decision = decide_flow(
        question="wedding, red",
        state=_state(),
        ontology=ProductOntology(),
    )

    assert decision.action == "UPDATE_FLOW_SLOTS"
    assert decision.active_category_key == "salwar_kameez"
    assert is_slot_update("wedding, red", ontology=ProductOntology()) is True


def test_fresh_product_question_starts_new_flow_not_slot_update() -> None:
    decision = decide_flow(
        question="red saree dekhao",
        state=_state(),
        ontology=ProductOntology(),
    )

    assert decision.action == "START_NEW_FLOW"
    assert is_slot_update("red saree dekhao", ontology=ProductOntology()) is False


def test_first_turn_product_question_starts_new_flow_without_active_category() -> None:
    decision = decide_flow(
        question="do you have Salwar Kameez?",
        state=ConversationState(session_id="new-session", turn_count=0),
        ontology=ProductOntology(),
    )

    assert decision.action == "START_NEW_FLOW"
    assert decision.active_category_key is None


def test_support_question_routes_away_from_shopping_flow() -> None:
    decision = decide_flow(
        question="delivery charge koto?",
        state=_state(),
        ontology=ProductOntology(),
    )

    assert decision.action == "SUPPORT_ROUTE"
    assert is_slot_update("delivery charge koto?", ontology=ProductOntology()) is False


def test_safety_question_routes_away_from_shopping_flow() -> None:
    decision = decide_flow(
        question="rash er jonno medicine ki khabo?",
        state=_state(),
        ontology=ProductOntology(),
    )

    assert decision.action == "SAFETY_ROUTE"
    assert is_slot_update("rash er jonno medicine ki khabo?", ontology=ProductOntology()) is False


def test_price_followup_continues_product_focus() -> None:
    decision = decide_flow(
        question="price koto?",
        state=_state(),
        ontology=ProductOntology(),
    )

    assert decision.action == "CONTINUE_PRODUCT_FOCUS"
    assert decision.active_category_key == "salwar_kameez"


def test_similar_followup_uses_current_anchor() -> None:
    decision = decide_flow(
        question="show similar cheaper",
        state=_state("shirt"),
        ontology=ProductOntology(),
    )

    assert decision.action == "COMPARE_OR_SIMILAR"
    assert decision.active_category_key == "shirt"


def test_flow_continuation_injects_active_category_filter() -> None:
    filters = filters_for_flow_continuation(
        base_filters=InventorySearchFilters(),
        state=_state(),
        ontology=ProductOntology(),
    )

    assert filters.categories == ["Salwar Kameez"]
    assert filters.min_stock == 1
