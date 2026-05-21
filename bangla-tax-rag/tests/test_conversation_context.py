from __future__ import annotations

from app.core.schemas import InventoryAskRequest
from app.inventory.conversation_context import (
    build_active_filters_from_state,
    hydrate_request_from_state,
    question_looks_like_followup,
    question_looks_like_new_request,
)
from app.inventory.conversation_state import ConversationState
from app.inventory.ontology import ProductOntology


def _state() -> ConversationState:
    return ConversationState(
        session_id="flow-1",
        last_shown_product_ids=["p-red", "p-blue", "p-green"],
        last_primary_product_id="p-red",
        last_intent="fashion_search",
        last_question="red saree dekhao under 3000",
        active_slots={"category_key": "saree", "color_family": "red", "budget_max": 3000},
        turn_count=2,
    )


def test_followup_detector_catches_banglish_price() -> None:
    assert question_looks_like_followup("etar dam koto?")
    assert question_looks_like_followup("M size ache?")
    assert question_looks_like_followup("same design blue ache?")


def test_new_request_detector_catches_product_type() -> None:
    assert question_looks_like_new_request("red saree ache?", ProductOntology())
    assert not question_looks_like_new_request("etar dam koto?", ProductOntology())


def test_hydrate_request_restores_focus_and_answer_plan_for_followup() -> None:
    request = InventoryAskRequest(question="second one er price koto?", session_id="flow-1")
    hydrated = hydrate_request_from_state(request=request, state=_state())

    assert hydrated.used_state
    assert hydrated.request.focused_product_ids == ["p-blue"]
    assert hydrated.request.last_answer_plan is not None
    assert hydrated.request.last_answer_plan.primary_product_id == "p-red"
    assert "Recent chat context" in hydrated.request.conversation_history[0].content


def test_hydrate_request_does_not_focus_old_product_for_fresh_request() -> None:
    request = InventoryAskRequest(question="black panjabi dekhao", session_id="flow-1")
    hydrated = hydrate_request_from_state(request=request, state=_state())

    assert hydrated.request.focused_product_ids == []
    assert hydrated.request.last_answer_plan is None
    assert hydrated.request.conversation_history


def test_build_active_filters_from_state_uses_category_and_budget() -> None:
    filters = build_active_filters_from_state(_state(), ontology=ProductOntology())
    assert filters is not None
    assert filters.categories == ["Saree"]
    assert filters.max_price == 3000
