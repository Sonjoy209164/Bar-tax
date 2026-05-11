"""Tests for the customer feedback route handler."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_feedback_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    from app.api import routes_feedback
    from app.inventory import feedback_to_eval

    feedback_path = tmp_path / "feedback.jsonl"
    pending_path = tmp_path / "pending_cases.jsonl"
    approved_path = tmp_path / "approved_cases.jsonl"
    monkeypatch.setattr(routes_feedback, "_FEEDBACK_PATH", feedback_path)
    monkeypatch.setattr(feedback_to_eval, "_FEEDBACK_PATH", feedback_path)
    monkeypatch.setattr(feedback_to_eval, "_PENDING_PATH", pending_path)
    monkeypatch.setattr(feedback_to_eval, "_APPROVED_PATH", approved_path)
    return {"feedback": feedback_path, "pending": pending_path, "approved": approved_path}


def test_downvote_feedback_creates_pending_eval_case(isolated_feedback_paths: dict[str, Path]) -> None:
    from app.api.routes_feedback import FeedbackRequest, submit_feedback
    from app.inventory import feedback_to_eval

    response = asyncio.run(
        submit_feedback(
            FeedbackRequest(
                session_id="session-1",
                question="office bag ache?",
                answer="I found sarees.",
                rating="down",
                comment="Wrong product category",
                intent="fashion_search",
                product_ids=["BAG-1", "BAG-1", ""],
                trace_id="trace-abc",
                confidence_score=0.33,
                abstained=False,
                answer_plan={
                    "intent": "fashion_search",
                    "primary_product_id": "BAG-1",
                    "debug_extra": "should not be stored",
                },
            )
        )
    )

    assert response.status == "saved"
    assert response.pending_case_created is True

    feedback_entry = json.loads(isolated_feedback_paths["feedback"].read_text(encoding="utf-8").splitlines()[0])
    assert feedback_entry["answer_plan"] == {
        "intent": "fashion_search",
        "primary_product_id": "BAG-1",
    }
    pending = feedback_to_eval.list_pending_cases()
    assert len(pending) == 1
    assert pending[0]["user_comment"] == "Wrong product category"
    assert pending[0]["trace_id"] == "trace-abc"
    assert pending[0]["product_ids"] == ["BAG-1"]


def test_upvote_feedback_does_not_create_pending_case(isolated_feedback_paths: dict[str, Path]) -> None:
    from app.api.routes_feedback import FeedbackRequest, submit_feedback

    response = asyncio.run(
        submit_feedback(
            FeedbackRequest(
                session_id="session-1",
                question="price?",
                answer="BDT 1,500.",
                rating="up",
            )
        )
    )

    assert response.status == "saved"
    assert response.pending_case_created is False
    assert not isolated_feedback_paths["pending"].exists()
