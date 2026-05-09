"""Tests for waitlist module."""
from pathlib import Path

import pytest

from app.inventory.waitlist import WaitlistEntry, WaitlistManager, check_restock_and_notify


@pytest.fixture(autouse=True)
def _patch_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.inventory.waitlist._WAITLIST_PATH", tmp_path / "waitlist.jsonl")


def test_add_and_retrieve() -> None:
    mgr = WaitlistManager()
    mgr.add(session_id="s1", product_id="p1", product_name="Red Saree", phone="01711000001")
    entries = mgr.get_waitlist("p1")
    assert len(entries) == 1
    assert entries[0].session_id == "s1"


def test_different_sessions_both_added() -> None:
    mgr = WaitlistManager()
    mgr.add(session_id="s1", product_id="p1", product_name="Saree")
    mgr.add(session_id="s2", product_id="p1", product_name="Saree")
    assert len(mgr.get_waitlist("p1")) == 2


def test_get_all_pending() -> None:
    mgr = WaitlistManager()
    mgr.add(session_id="s1", product_id="p1", product_name="Saree")
    mgr.add(session_id="s2", product_id="p2", product_name="Panjabi")
    pending = mgr.get_all_pending()
    assert len(pending) == 2
    assert all(isinstance(e, WaitlistEntry) for e in pending)


def test_mark_notified_removes_from_pending() -> None:
    mgr = WaitlistManager()
    mgr.add(session_id="s1", product_id="p1", product_name="Saree")
    mgr.mark_notified("p1")
    assert mgr.get_waitlist("p1") == []


def test_mark_notified_returns_phones() -> None:
    mgr = WaitlistManager()
    mgr.add(session_id="s1", product_id="p1", product_name="Saree", phone="01711000001")
    phones = mgr.mark_notified("p1")
    assert "01711000001" in phones


def test_is_waitlist_request_english() -> None:
    mgr = WaitlistManager()
    assert mgr.is_waitlist_request("notify me when back in stock")


def test_is_waitlist_request_bangla() -> None:
    mgr = WaitlistManager()
    assert mgr.is_waitlist_request("কবে আসবে?")


def test_is_not_waitlist_request() -> None:
    mgr = WaitlistManager()
    assert not mgr.is_waitlist_request("show me red sarees")


def test_get_status_returns_dict() -> None:
    mgr = WaitlistManager()
    mgr.add(session_id="s1", product_id="p1", product_name="Saree")
    status = mgr.get_status()
    assert isinstance(status, dict)
    assert status["total_entries"] >= 1
    assert status["pending_notifications"] >= 1


def test_get_waitlist_empty_product() -> None:
    mgr = WaitlistManager()
    assert mgr.get_waitlist("nonexistent") == []


def test_check_restock_notify_triggers_on_zero_to_positive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Already patched via autouse fixture
    mgr = WaitlistManager()
    mgr.add(session_id="s1", product_id="p1", product_name="Saree", phone="01711000002")
    phones = check_restock_and_notify("p1", new_stock=5, old_stock=0, product_name="Saree")
    assert "01711000002" in phones


def test_check_restock_notify_no_trigger_when_already_in_stock() -> None:
    phones = check_restock_and_notify("p1", new_stock=5, old_stock=3, product_name="Saree")
    assert phones == []
