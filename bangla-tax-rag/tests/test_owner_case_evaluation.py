"""Tests for owner-approved feedback case evaluation."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest


def test_evaluate_approved_cases_runs_current_bot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import routes_owner
    from app.inventory import feedback_to_eval

    approved_path = tmp_path / "approved_cases.jsonl"
    monkeypatch.setattr(feedback_to_eval, "_APPROVED_PATH", approved_path)
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    approved_path.write_text(
        json.dumps(
            {
                "case_id": "CASE-FB-1",
                "feedback_id": "FB-1",
                "question": "office bag ache?",
                "expected_intent": "fashion_search",
                "expected_product_ids": ["BAG-1"],
                "expected_substring": "office",
                "must_not_contain": ["saree"],
                "status": "approved",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeResponse:
        def model_dump(self, mode: str = "json") -> dict[str, Any]:
            return {
                "answer": "Office use er jonno BAG-1 available.",
                "recommended_product_ids": ["BAG-1"],
                "answer_plan": {"intent": "fashion_search"},
            }

    class FakeService:
        def ask(self, request: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(routes_owner, "get_inventory_service", lambda: FakeService())

    body = asyncio.run(routes_owner.evaluate_approved_cases())

    assert body["total"] == 1
    assert body["passed"] == 1
    assert body["failed"] == 0
    assert body["results"][0]["passed"] is True
