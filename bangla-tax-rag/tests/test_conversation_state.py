"""Tests for ConversationState + ConversationStateStore."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.inventory.conversation_state import (
    ConversationState,
    ConversationStateStore,
)


@pytest.fixture
def store(tmp_path: Path) -> ConversationStateStore:
    return ConversationStateStore(db_path=tmp_path / "state.sqlite")


# ── ConversationState dataclass ───────────────────────────────────────────────

def test_serialize_roundtrip() -> None:
    s = ConversationState(
        session_id="sid-1",
        last_shown_product_ids=["p1", "p2"],
        last_intent="fashion_search",
        color_counts={"red": 2},
        turn_count=3,
    )
    text = s.to_json()
    s2 = ConversationState.from_json(text, session_id="sid-1")
    assert s2.session_id == "sid-1"
    assert s2.last_shown_product_ids == ["p1", "p2"]
    assert s2.color_counts == {"red": 2}
    assert s2.turn_count == 3


def test_from_json_invalid_returns_empty() -> None:
    s = ConversationState.from_json("not json", session_id="sid-1")
    assert s.session_id == "sid-1"
    assert s.last_shown_product_ids == []


# ── ConversationStateStore CRUD ───────────────────────────────────────────────

def test_get_returns_empty_state_when_unknown_session(store: ConversationStateStore) -> None:
    s = store.get("never-seen")
    assert s.session_id == "never-seen"
    assert s.turn_count == 0


def test_save_and_get_roundtrip(store: ConversationStateStore) -> None:
    s = ConversationState(session_id="abc", last_intent="fashion_search", turn_count=5)
    store.save(s)
    loaded = store.get("abc")
    assert loaded.last_intent == "fashion_search"
    assert loaded.turn_count == 5


def test_clear_removes_state(store: ConversationStateStore) -> None:
    s = ConversationState(session_id="abc", turn_count=2)
    store.save(s)
    store.clear("abc")
    loaded = store.get("abc")
    assert loaded.turn_count == 0


def test_get_with_empty_session_returns_safely(store: ConversationStateStore) -> None:
    s = store.get("")
    assert s.session_id == ""


# ── record_turn updates everything correctly ──────────────────────────────────

def test_record_turn_increments_count(store: ConversationStateStore) -> None:
    state = store.record_turn(
        session_id="sid",
        question="red saree",
        intent="fashion_search",
        slots={"category_key": "saree", "color_family": "red"},
        product_ids=["p1", "p2"],
        primary_product_id="p1",
        confidence=0.9,
        abstained=False,
    )
    assert state.turn_count == 1
    state2 = store.record_turn(
        session_id="sid",
        question="any blue?",
        intent="fashion_search",
        slots={"category_key": "saree", "color_family": "blue"},
        product_ids=["p3"],
        primary_product_id="p3",
        confidence=0.85,
        abstained=False,
    )
    assert state2.turn_count == 2


def test_record_turn_counts_colors_and_categories(store: ConversationStateStore) -> None:
    for color in ("red", "red", "blue", "red"):
        store.record_turn(
            session_id="sid",
            question="x",
            intent="fashion_search",
            slots={"category_key": "saree", "color_family": color},
            product_ids=[],
            primary_product_id=None,
            confidence=0.8,
            abstained=False,
        )
    state = store.get("sid")
    assert state.color_counts == {"red": 3, "blue": 1}
    assert state.category_counts == {"saree": 4}


def test_record_turn_tracks_consecutive_failures(store: ConversationStateStore) -> None:
    for _ in range(3):
        store.record_turn(
            session_id="sid",
            question="x",
            intent="fashion_search",
            slots={},
            product_ids=[],
            primary_product_id=None,
            confidence=0.4,
            abstained=False,
        )
    state = store.get("sid")
    assert state.consecutive_failures == 3


def test_record_turn_resets_failures_on_success(store: ConversationStateStore) -> None:
    store.record_turn(session_id="sid", question="x", intent="fs", slots={},
                     product_ids=[], primary_product_id=None,
                     confidence=0.3, abstained=False)
    store.record_turn(session_id="sid", question="x", intent="fs", slots={},
                     product_ids=["p1"], primary_product_id="p1",
                     confidence=0.92, abstained=False)
    state = store.get("sid")
    assert state.consecutive_failures == 0


def test_record_turn_persists_last_shown_products(store: ConversationStateStore) -> None:
    store.record_turn(
        session_id="sid",
        question="red saree",
        intent="fashion_search",
        slots={},
        product_ids=["p1", "p2", "p3"],
        primary_product_id="p1",
        confidence=0.9,
        abstained=False,
    )
    state = store.get("sid")
    assert state.last_shown_product_ids == ["p1", "p2", "p3"]
    assert state.last_primary_product_id == "p1"


def test_budget_observations_capped_to_last_10(store: ConversationStateStore) -> None:
    for i in range(15):
        store.record_turn(
            session_id="sid",
            question="x",
            intent="fashion_search",
            slots={"budget_max": float(1000 + i * 100)},
            product_ids=[],
            primary_product_id=None,
            confidence=0.8,
            abstained=False,
        )
    state = store.get("sid")
    assert len(state.budget_observations) == 10
