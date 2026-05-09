"""Tests for the feedback → eval-case pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.inventory import feedback_to_eval


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    fb = tmp_path / "feedback.jsonl"
    pending = tmp_path / "pending.jsonl"
    approved = tmp_path / "approved.jsonl"
    monkeypatch.setattr(feedback_to_eval, "_FEEDBACK_PATH", fb)
    monkeypatch.setattr(feedback_to_eval, "_PENDING_PATH", pending)
    monkeypatch.setattr(feedback_to_eval, "_APPROVED_PATH", approved)
    return {"fb": fb, "pending": pending, "approved": approved}


def _write_feedback(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


# ── harvesting ───────────────────────────────────────────────────────────────

def test_harvest_creates_pending_cases_for_thumbs_down(isolated_paths: dict[str, Path]) -> None:
    _write_feedback(
        isolated_paths["fb"],
        [
            {"feedback_id": "FB-1", "rating": "down", "question": "kichu", "answer": "...", "intent": "fashion_search", "comment": "wrong"},
            {"feedback_id": "FB-2", "rating": "up",   "question": "ok",     "answer": "...", "intent": "fashion_search"},
        ],
    )
    n = feedback_to_eval.harvest_bad_feedback_to_pending()
    assert n == 1
    pending = feedback_to_eval.list_pending_cases()
    assert len(pending) == 1
    assert pending[0]["feedback_id"] == "FB-1"


def test_harvest_is_idempotent(isolated_paths: dict[str, Path]) -> None:
    _write_feedback(isolated_paths["fb"], [
        {"feedback_id": "FB-1", "rating": "down", "question": "x", "answer": "y", "intent": "fashion_search"}
    ])
    feedback_to_eval.harvest_bad_feedback_to_pending()
    n_second = feedback_to_eval.harvest_bad_feedback_to_pending()
    assert n_second == 0
    assert len(feedback_to_eval.list_pending_cases()) == 1


def test_harvest_empty_feedback(isolated_paths: dict[str, Path]) -> None:
    n = feedback_to_eval.harvest_bad_feedback_to_pending()
    assert n == 0


# ── approval ─────────────────────────────────────────────────────────────────

def test_approve_moves_case_from_pending_to_approved(isolated_paths: dict[str, Path]) -> None:
    _write_feedback(isolated_paths["fb"], [
        {"feedback_id": "FB-1", "rating": "down", "question": "?",
         "answer": "wrong", "intent": "fashion_search"}
    ])
    feedback_to_eval.harvest_bad_feedback_to_pending()
    case_id = feedback_to_eval.list_pending_cases()[0]["case_id"]

    ok = feedback_to_eval.approve_case(
        case_id=case_id,
        expected_intent="fashion_clarification",
        expected_substring="কোন ধরনের",
        notes="should clarify",
    )
    assert ok is True

    pending = feedback_to_eval.list_pending_cases()
    assert pending == []

    approved = feedback_to_eval.list_approved_cases()
    assert len(approved) == 1
    assert approved[0]["expected_intent"] == "fashion_clarification"
    assert approved[0]["status"] == "approved"
    assert approved[0]["notes"] == "should clarify"


def test_approve_unknown_case_returns_false(isolated_paths: dict[str, Path]) -> None:
    ok = feedback_to_eval.approve_case(case_id="CASE-DOES-NOT-EXIST")
    assert ok is False


def test_approved_cases_are_persistent(isolated_paths: dict[str, Path]) -> None:
    _write_feedback(isolated_paths["fb"], [
        {"feedback_id": "FB-1", "rating": "down", "question": "x", "answer": "y", "intent": "fashion_search"}
    ])
    feedback_to_eval.harvest_bad_feedback_to_pending()
    case_id = feedback_to_eval.list_pending_cases()[0]["case_id"]
    feedback_to_eval.approve_case(case_id=case_id, expected_intent="fashion_search")
    # New harvest after approval should NOT recreate the case
    feedback_to_eval.harvest_bad_feedback_to_pending()
    assert feedback_to_eval.list_pending_cases() == []
    assert len(feedback_to_eval.list_approved_cases()) == 1
