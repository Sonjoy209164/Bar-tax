"""Tests for identity_store module."""
from pathlib import Path

import pytest

from app.inventory.identity_store import IdentityStore


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> IdentityStore:
    monkeypatch.setattr("app.inventory.identity_store._DB_PATH", tmp_path / "identity.sqlite")
    return IdentityStore()


def test_upsert_and_get_profile(store: IdentityStore) -> None:
    store.upsert_profile("01711000001", {"name": "Rima", "phone": "01711000001"})
    profile = store.get_profile("01711000001")
    assert profile is not None
    assert profile["name"] == "Rima"


def test_get_profile_nonexistent(store: IdentityStore) -> None:
    assert store.get_profile("00000000000") is None


def test_link_and_resolve_session(store: IdentityStore) -> None:
    store.upsert_profile("01711000002", {"phone": "01711000002", "color": "blue"})
    store.link_session("sess-abc", "01711000002")
    phone = store.get_phone_for_session("sess-abc")
    assert phone == "01711000002"


def test_get_or_create_profile_with_phone(store: IdentityStore) -> None:
    profile = store.get_or_create_profile("sess-xyz", phone="01711000003")
    assert profile["phone"] == "01711000003"


def test_get_or_create_profile_transient_no_phone(store: IdentityStore) -> None:
    profile = store.get_or_create_profile("sess-anon")
    assert "session_id" in profile
    assert profile.get("phone") is None


def test_save_and_reload_profile(store: IdentityStore) -> None:
    store.link_session("sess-1", "01711000004")
    store.save_session_profile("sess-1", {"phone": "01711000004", "budget_max": 3000})
    profile = store.get_profile("01711000004")
    assert profile is not None
    assert profile["budget_max"] == 3000


def test_delete_profile(store: IdentityStore) -> None:
    store.upsert_profile("01711000005", {"phone": "01711000005"})
    deleted = store.delete_profile("01711000005")
    assert deleted is True
    assert store.get_profile("01711000005") is None


def test_known_customer_count(store: IdentityStore) -> None:
    store.upsert_profile("01711000010", {"phone": "01711000010"})
    store.upsert_profile("01711000011", {"phone": "01711000011"})
    assert store.known_customer_count() >= 2


def test_recent_sessions(store: IdentityStore) -> None:
    store.link_session("sess-r1", "01711000020")
    sessions = store.recent_sessions(limit=10)
    assert any(s["session_id"] == "sess-r1" for s in sessions)
