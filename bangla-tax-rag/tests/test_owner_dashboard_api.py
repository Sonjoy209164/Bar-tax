"""Smoke tests for the /owner dashboard API."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolate_data_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect every storage path the routes touch to tmp_path."""
    from app.inventory import escalation, feedback_to_eval, conversion_tracker
    monkeypatch.setattr(escalation, "_NOTIFICATIONS_PATH", tmp_path / "esc.jsonl")
    monkeypatch.setattr(feedback_to_eval, "_FEEDBACK_PATH", tmp_path / "fb.jsonl")
    monkeypatch.setattr(feedback_to_eval, "_PENDING_PATH", tmp_path / "pending.jsonl")
    monkeypatch.setattr(feedback_to_eval, "_APPROVED_PATH", tmp_path / "approved.jsonl")
    monkeypatch.setattr(conversion_tracker, "_LOG_PATH", tmp_path / "conv.jsonl")


@pytest.fixture
def client() -> TestClient:
    os.environ["API_KEY"] = "test-key-owner"
    from app.main import app
    return TestClient(app)


_HEADERS = {"X-API-Key": "test-key-owner"}


# ── /owner/summary ───────────────────────────────────────────────────────────

def test_summary_empty(client: TestClient) -> None:
    r = client.get("/owner/summary", headers=_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["shown_total"] == 0
    assert body["conversion_rate"] is None


def test_summary_clamps_window(client: TestClient) -> None:
    r = client.get("/owner/summary?days=500", headers=_HEADERS)
    assert r.status_code == 200
    assert r.json()["window_days"] in (90, 0)  # clamped to 90 max


# ── /owner/escalations ───────────────────────────────────────────────────────

def test_list_escalations_empty(client: TestClient) -> None:
    r = client.get("/owner/escalations", headers=_HEADERS)
    assert r.status_code == 200
    assert r.json() == []


def test_resolve_unknown_escalation_returns_404(client: TestClient) -> None:
    r = client.post("/owner/escalations/ESC-DOES-NOT-EXIST/resolve", headers=_HEADERS)
    assert r.status_code == 404


# ── /owner/cases/* ───────────────────────────────────────────────────────────

def test_pending_cases_empty(client: TestClient) -> None:
    r = client.get("/owner/cases/pending", headers=_HEADERS)
    assert r.status_code == 200
    assert r.json() == []


def test_harvest_returns_zero_when_no_feedback(client: TestClient) -> None:
    r = client.post("/owner/cases/harvest", headers=_HEADERS)
    assert r.status_code == 200
    assert r.json()["new_pending_cases"] == 0


def test_approve_unknown_case_returns_404(client: TestClient) -> None:
    r = client.post(
        "/owner/cases/approve",
        headers=_HEADERS,
        json={"case_id": "CASE-DOES-NOT-EXIST"},
    )
    assert r.status_code == 404


def test_approved_cases_initially_empty(client: TestClient) -> None:
    r = client.get("/owner/cases/approved", headers=_HEADERS)
    assert r.status_code == 200
    assert r.json() == []
