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
            {
                "feedback_id": "FB-1",
                "rating": "down",
                "question": "kichu",
                "answer": "...",
                "intent": "fashion_search",
                "comment": "wrong",
                "trace_id": "trace-1",
                "confidence_score": 0.42,
                "product_ids": ["SAREE-1", "SAREE-1", ""],
                "abstained": False,
            },
            {"feedback_id": "FB-2", "rating": "up",   "question": "ok",     "answer": "...", "intent": "fashion_search"},
        ],
    )
    n = feedback_to_eval.harvest_bad_feedback_to_pending()
    assert n == 1
    pending = feedback_to_eval.list_pending_cases()
    assert len(pending) == 1
    assert pending[0]["feedback_id"] == "FB-1"
    assert pending[0]["trace_id"] == "trace-1"
    assert pending[0]["confidence_score"] == 0.42
    assert pending[0]["product_ids"] == ["SAREE-1"]


def test_create_pending_case_from_live_feedback(isolated_paths: dict[str, Path]) -> None:
    created = feedback_to_eval.create_pending_case_from_feedback(
        {
            "feedback_id": "FB-LIVE-1",
            "rating": "down",
            "question": "same design red ase?",
            "answer": "No red option.",
            "intent": "same_design_variant",
            "comment": "There is a red variant in catalog",
            "trace_id": "trace-live",
            "confidence_score": "0.58",
            "product_ids": ["SAREE-RED"],
            "abstained": False,
            "abstention_reason": None,
        }
    )

    assert created is True
    assert feedback_to_eval.create_pending_case_from_feedback({"feedback_id": "FB-LIVE-1", "rating": "down"}) is False
    pending = feedback_to_eval.list_pending_cases()
    assert len(pending) == 1
    assert pending[0]["case_id"] == "CASE-FB-LIVE-1"
    assert pending[0]["user_comment"] == "There is a red variant in catalog"
    assert pending[0]["trace_id"] == "trace-live"
    assert pending[0]["confidence_score"] == 0.58
    assert pending[0]["product_ids"] == ["SAREE-RED"]


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


# ── deterministic evaluation ────────────────────────────────────────────────

def test_evaluate_case_against_response_passes_on_concrete_expectations() -> None:
    case = {
        "case_id": "CASE-1",
        "feedback_id": "FB-1",
        "question": "eid er jonno saree",
        "expected_intent": "fashion_search",
        "expected_product_ids": ["SAREE-1"],
        "expected_substring": "BDT 4,500",
        "must_not_contain": ["out of stock"],
    }
    response = {
        "answer": "This elegant saree is available for BDT 4,500.",
        "recommended_product_ids": ["SAREE-1"],
        "answer_plan": {"intent": "fashion_search"},
    }

    result = feedback_to_eval.evaluate_case_against_response(case, response)

    assert result["passed"] is True
    assert result["issues"] == []


def test_evaluate_case_against_response_reports_failures() -> None:
    case = {
        "case_id": "CASE-2",
        "feedback_id": "FB-2",
        "question": "office bag",
        "expected_intent": "fashion_search",
        "expected_product_ids": ["BAG-2"],
        "expected_substring": "office",
        "must_not_contain": ["saree"],
    }
    response = {
        "answer": "I found a saree.",
        "recommended_product_ids": ["SAREE-1"],
        "answer_plan": {"intent": "small_talk"},
    }

    result = feedback_to_eval.evaluate_case_against_response(case, response)

    assert result["passed"] is False
    assert "Expected intent 'fashion_search', got 'small_talk'." in result["issues"]
    assert "Missing expected product ids: BAG-2." in result["issues"]
    assert "Expected answer to contain 'office'." in result["issues"]
    assert "Answer must not contain 'saree'." in result["issues"]
