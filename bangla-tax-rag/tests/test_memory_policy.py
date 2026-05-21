from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.schemas import InventoryAskRequest
from app.inventory.conversation_context import hydrate_request_from_state
from app.inventory.conversation_state import ConversationState, ConversationStateStore
from app.inventory.memory_policy import (
    PRODUCT_FOCUS_TTL_SECONDS,
    product_focus_expired,
    should_use_product_focus,
    to_iso,
)


def _fresh_state() -> ConversationState:
    now = datetime.now(timezone.utc)
    return ConversationState(
        session_id="sid",
        last_shown_product_ids=["p1", "p2"],
        last_primary_product_id="p1",
        turn_count=1,
        product_focus_source="text_search",
        product_focus_updated_at=to_iso(now),
        product_focus_expires_at=to_iso(now + timedelta(seconds=PRODUCT_FOCUS_TTL_SECONDS)),
        product_focus_ttl_seconds=PRODUCT_FOCUS_TTL_SECONDS,
        product_focus_confidence=0.91,
    )


def test_product_focus_policy_allows_clear_followup_inside_ttl() -> None:
    state = _fresh_state()
    decision = should_use_product_focus(question="etar dam koto?", state=state)

    assert decision.allowed is True
    assert decision.source == "text_search"
    assert decision.confidence == 0.91
    assert decision.expired is False


def test_product_focus_policy_blocks_expired_focus() -> None:
    state = _fresh_state()
    state.product_focus_updated_at = to_iso(datetime.now(timezone.utc) - timedelta(hours=2))
    state.product_focus_expires_at = to_iso(datetime.now(timezone.utc) - timedelta(hours=1))

    decision = should_use_product_focus(question="etar dam koto?", state=state)

    assert decision.allowed is False
    assert decision.expired is True
    assert "expired" in decision.reason


def test_product_focus_policy_blocks_new_explicit_product_request() -> None:
    state = _fresh_state()
    decision = should_use_product_focus(question="red saree dekhao", state=state)

    assert decision.allowed is False
    assert "new explicit" in decision.reason


def test_record_turn_writes_product_focus_metadata(tmp_path: Path) -> None:
    store = ConversationStateStore(db_path=tmp_path / "state.sqlite")
    state = store.record_turn(
        session_id="sid",
        question="black panjabi dekhao",
        intent="fashion_search",
        slots={"category_key": "panjabi", "color_family": "black"},
        product_ids=["p1", "p2"],
        primary_product_id="p1",
        confidence=0.88,
        abstained=False,
        memory_source="text_search",
        write_reason="test write",
    )

    assert state.last_shown_product_ids == ["p1", "p2"]
    assert state.product_focus_source == "text_search"
    assert state.product_focus_confidence == 0.88
    assert state.product_focus_ttl_seconds > 0
    assert state.product_focus_expires_at
    assert state.product_focus_write_reason == "test write"
    assert "category_key" in state.slot_memory_meta


def test_record_turn_blocks_unsafe_preference_memory(tmp_path: Path) -> None:
    store = ConversationStateStore(db_path=tmp_path / "state.sqlite")
    store.record_turn(
        session_id="sid",
        question="red saree dekhao",
        intent="fashion_search",
        slots={"category_key": "saree", "color_family": "red"},
        product_ids=["p1"],
        primary_product_id="p1",
        confidence=0.9,
        abstained=False,
    )
    state = store.record_turn(
        session_id="sid",
        question="rash er jonno kon medicine khabo?",
        intent="medical_or_health_advice",
        slots={"category_key": "wellness", "color_family": "green", "risk_level": "high"},
        product_ids=["bad-product"],
        primary_product_id="bad-product",
        confidence=0.9,
        abstained=True,
    )

    assert state.last_shown_product_ids == ["p1"]
    assert state.last_primary_product_id == "p1"
    assert state.active_slots["category_key"] == "saree"
    assert state.color_counts == {"red": 1}
    assert "wellness" not in state.category_counts


def test_expired_focus_is_not_hydrated_from_server_state() -> None:
    state = _fresh_state()
    state.product_focus_updated_at = to_iso(datetime.now(timezone.utc) - timedelta(hours=2))
    state.product_focus_expires_at = to_iso(datetime.now(timezone.utc) - timedelta(hours=1))
    assert product_focus_expired(state)

    request = InventoryAskRequest(
        question="etar price koto?",
        session_id="sid",
        focused_product_ids=["stale-ui-p1"],
    )
    hydrated = hydrate_request_from_state(request=request, state=state)

    assert hydrated.used_state is True
    assert hydrated.request.focused_product_ids == []
    assert hydrated.request.last_answer_plan is None
    assert "ignored_expired_product_focus" in (hydrated.reason or "")
