"""Tests for the preference learner."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.inventory.conversation_state import ConversationState
from app.inventory.preference_learner import (
    apply_preferences_to_profile,
    derive_preferences,
)


# ── derive_preferences ───────────────────────────────────────────────────────

def test_no_preferences_when_state_empty() -> None:
    s = ConversationState(session_id="x")
    assert derive_preferences(s) == {}


def test_color_repeated_three_times_becomes_favorite() -> None:
    s = ConversationState(session_id="x", color_counts={"red": 3, "blue": 1})
    p = derive_preferences(s)
    assert p["favorite_colors"] == ["red"]


def test_color_under_threshold_not_recorded() -> None:
    s = ConversationState(session_id="x", color_counts={"red": 2})
    p = derive_preferences(s)
    assert "favorite_colors" not in p


def test_categories_sorted_by_count_descending() -> None:
    s = ConversationState(session_id="x", category_counts={"saree": 4, "kurti": 5, "blouse": 3})
    p = derive_preferences(s)
    assert p["preferred_categories"] == ["kurti", "saree", "blouse"]


def test_occasion_repeated_twice_recorded() -> None:
    s = ConversationState(session_id="x", occasion_counts={"wedding": 2, "casual": 1})
    p = derive_preferences(s)
    assert p["preferred_occasion"] == "wedding"


def test_occasion_only_once_not_recorded() -> None:
    s = ConversationState(session_id="x", occasion_counts={"wedding": 1})
    p = derive_preferences(s)
    assert "preferred_occasion" not in p


def test_typical_budget_is_median() -> None:
    s = ConversationState(session_id="x", budget_observations=[3000, 5000, 7000])
    p = derive_preferences(s)
    assert p["typical_budget"] == 5000


def test_budget_single_observation_ignored() -> None:
    s = ConversationState(session_id="x", budget_observations=[5000])
    p = derive_preferences(s)
    assert "typical_budget" not in p


# ── apply_preferences_to_profile ─────────────────────────────────────────────

def test_apply_skips_when_no_phone() -> None:
    s = ConversationState(session_id="x", color_counts={"red": 5})
    store = MagicMock()
    patch = apply_preferences_to_profile(state=s, identity_store=store, phone=None)
    assert patch == {}
    store.upsert_profile.assert_not_called()


def test_apply_skips_when_no_preferences() -> None:
    s = ConversationState(session_id="x")  # nothing repeated
    store = MagicMock()
    patch = apply_preferences_to_profile(state=s, identity_store=store, phone="01711000000")
    assert patch == {}
    store.upsert_profile.assert_not_called()


def test_apply_writes_merged_profile() -> None:
    s = ConversationState(session_id="x", color_counts={"red": 3})
    store = MagicMock()
    store.get_profile.return_value = {"phone": "01711000000", "name": "Sumi"}
    patch = apply_preferences_to_profile(state=s, identity_store=store, phone="01711000000")
    assert patch == {"favorite_colors": ["red"]}
    # upsert called with merged dict
    store.upsert_profile.assert_called_once()
    args, _ = store.upsert_profile.call_args
    assert args[0] == "01711000000"
    assert args[1]["favorite_colors"] == ["red"]
    assert args[1]["name"] == "Sumi"  # existing field preserved


def test_apply_unions_list_values() -> None:
    """If profile already has favorite_colors, new ones are merged not replaced."""
    s = ConversationState(session_id="x", color_counts={"red": 3, "navy": 4})
    store = MagicMock()
    store.get_profile.return_value = {"favorite_colors": ["pink", "red"]}
    apply_preferences_to_profile(state=s, identity_store=store, phone="01711000000")
    args, _ = store.upsert_profile.call_args
    written_colors = args[1]["favorite_colors"]
    # New high-count colors (navy first, then red) ahead of existing pink
    assert written_colors[0] == "navy"
    assert "red" in written_colors
    assert "pink" in written_colors
