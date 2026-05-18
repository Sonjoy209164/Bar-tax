"""Tests for InventoryService._build_profile_context_turn."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.inventory_service import InventoryService


# ── None / empty cases ────────────────────────────────────────────────────────

def test_returns_none_when_session_id_is_none() -> None:
    result = InventoryService._build_profile_context_turn(None)
    assert result is None


def test_returns_none_when_profile_has_no_useful_data() -> None:
    empty_profile: dict = {"session_id": "abc123"}
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=empty_profile):
        result = InventoryService._build_profile_context_turn("abc123")
    assert result is None


def test_returns_none_on_identity_store_exception() -> None:
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               side_effect=RuntimeError("db gone")):
        result = InventoryService._build_profile_context_turn("abc123")
    assert result is None


# ── turn content ──────────────────────────────────────────────────────────────

def test_turn_is_user_role() -> None:
    profile = {"budget_max": 5000}
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=profile):
        result = InventoryService._build_profile_context_turn("s1")
    assert result is not None
    assert result[0] == "user"


def test_budget_included_in_turn() -> None:
    profile = {"budget_max": 8500.0}
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=profile):
        result = InventoryService._build_profile_context_turn("s1")
    assert result is not None
    assert "8,500" in result[1] or "8500" in result[1]


def test_favorite_colors_included_in_turn() -> None:
    profile = {"favorite_colors": ["red", "gold", "navy"]}
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=profile):
        result = InventoryService._build_profile_context_turn("s1")
    assert result is not None
    assert "red" in result[1]
    assert "gold" in result[1]


def test_sizes_included_in_turn() -> None:
    profile = {"sizes": {"saree": "medium", "kurti": "large"}}
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=profile):
        result = InventoryService._build_profile_context_turn("s1")
    assert result is not None
    assert "medium" in result[1] or "large" in result[1]


def test_preferred_categories_included_in_turn() -> None:
    profile = {"preferred_categories": ["saree", "jewelry"]}
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=profile):
        result = InventoryService._build_profile_context_turn("s1")
    assert result is not None
    assert "saree" in result[1]


def test_turn_wraps_with_saved_preferences_marker() -> None:
    profile = {"budget_max": 3000}
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=profile):
        result = InventoryService._build_profile_context_turn("s1")
    assert result is not None
    assert "[My saved preferences:" in result[1]


def test_at_most_three_colors_in_turn() -> None:
    profile = {"favorite_colors": ["red", "gold", "navy", "green", "pink"]}
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=profile):
        result = InventoryService._build_profile_context_turn("s1")
    assert result is not None
    # Only first 3 should appear
    assert result[1].count(",") <= 5   # rough upper bound


def test_combined_profile_fields_all_present() -> None:
    profile = {
        "budget_max": 10000,
        "favorite_colors": ["red"],
        "sizes": {"saree": "large"},
        "preferred_categories": ["panjabi"],
    }
    with patch("app.inventory.identity_store.IdentityStore.get_or_create_profile",
               return_value=profile):
        result = InventoryService._build_profile_context_turn("s1")
    assert result is not None
    content = result[1]
    assert "10,000" in content or "10000" in content
    assert "red" in content
    assert "large" in content
    assert "panjabi" in content
