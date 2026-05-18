from __future__ import annotations

import pytest
from app.inventory.customer_profile import CustomerProfileManager, CustomerProfile


def _manager(session_id: str = "test-session-001") -> CustomerProfileManager:
    return CustomerProfileManager(session_id)


def test_fresh_profile_is_empty():
    mgr = _manager("test-empty-001")
    assert mgr.profile.is_empty()


def test_extract_shoe_size():
    mgr = _manager("test-size-001")
    updates = mgr.extract_and_update("amar shoe size 42")
    assert any("42" in u for u in updates) or mgr.profile.sizes.get("shoe") == "42"


def test_extract_general_size():
    mgr = _manager("test-size-002")
    mgr.extract_and_update("size L lagbe")
    assert mgr.profile.sizes.get("general") == "L" or "general" in mgr.profile.sizes or "top" in mgr.profile.sizes


def test_extract_budget():
    mgr = _manager("test-budget-001")
    updates = mgr.extract_and_update("amar budget normally 3000 er moddhe")
    assert mgr.profile.budget_max == 3000.0 or any("3000" in u for u in updates)


def test_extract_skin_type_oily():
    mgr = _manager("test-skin-001")
    mgr.extract_and_update("amar oily skin")
    assert mgr.profile.skin_type == "oily"


def test_extract_skin_type_dry():
    mgr = _manager("test-skin-002")
    mgr.extract_and_update("amar dry skin")
    assert mgr.profile.skin_type == "dry"


def test_profile_summary_shows_saved_data():
    mgr = _manager("test-summary-001")
    mgr.profile.skin_type = "oily"
    mgr.profile.budget_max = 5000.0
    mgr.profile.sizes["shoe"] = "42"
    summary = mgr.profile.summary_text()
    assert "oily" in summary.lower()
    assert "5,000" in summary or "5000" in summary


def test_profile_summary_empty():
    mgr = _manager("test-summary-empty-001")
    summary = mgr.profile.summary_text()
    assert "no saved preferences" in summary.lower()


def test_is_forget_request():
    mgr = _manager("test-forget-001")
    assert mgr.is_forget_request("amar preference delete kore dao")
    assert mgr.is_forget_request("forget my preferences")
    assert mgr.is_forget_request("amar memory delete")


def test_is_show_request():
    mgr = _manager("test-show-001")
    assert mgr.is_show_request("amar saved preference ki")
    assert mgr.is_show_request("show my preferences")
    assert mgr.is_show_request("what are my preferences")


def test_reset_clears_profile():
    mgr = _manager("test-reset-001")
    mgr.profile.skin_type = "oily"
    mgr.profile.budget_max = 3000.0
    mgr.reset()
    assert mgr.profile.is_empty()


def test_profile_to_dict_and_from_dict():
    profile = CustomerProfile(session_id="roundtrip-001")
    profile.skin_type = "oily"
    profile.budget_max = 2500.0
    profile.sizes["shoe"] = "42"
    profile.favorite_colors.append("red")
    d = profile.to_dict()
    restored = CustomerProfile.from_dict(d)
    assert restored.skin_type == "oily"
    assert restored.budget_max == 2500.0
    assert restored.sizes.get("shoe") == "42"
    assert "red" in restored.favorite_colors


def test_multiple_sessions_independent():
    mgr1 = _manager("test-multi-001")
    mgr2 = _manager("test-multi-002")
    mgr1.profile.skin_type = "oily"
    mgr2.profile.skin_type = "dry"
    assert mgr1.profile.skin_type != mgr2.profile.skin_type
