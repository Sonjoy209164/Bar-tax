"""
Regression on the real-customer labeled set.

This test is intentionally lenient on size — it activates only once you have
at least 10 labeled rows in evaluation/offtopic_real_labeled.jsonl. Below
that, it skips so a clean checkout still passes CI.

When real data lands, this test enforces:
  - intent matches the label (per row)
  - risk_level matches the label (per row)
  - aggregate intent accuracy ≥ 0.85 on the full set
  - risk accuracy = 1.00 on high/critical rows
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.inventory.polite_boundary import classify_polite_boundary

LABELED_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "offtopic_real_labeled.jsonl"
MIN_ROWS_TO_ENFORCE = 10


def _load_rows() -> list[dict]:
    if not LABELED_PATH.exists():
        return []
    rows: list[dict] = []
    with LABELED_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


@pytest.fixture(scope="module")
def labeled_rows() -> list[dict]:
    rows = _load_rows()
    if len(rows) < MIN_ROWS_TO_ENFORCE:
        pytest.skip(
            f"only {len(rows)} labeled rows; need ≥{MIN_ROWS_TO_ENFORCE} "
            "to enforce regression — see evaluation/labeling_guide.md"
        )
    return rows


def test_aggregate_intent_accuracy(labeled_rows: list[dict]) -> None:
    total = len(labeled_rows)
    correct = 0
    for row in labeled_rows:
        decision = classify_polite_boundary(row["question"])
        got = decision.boundary_type if decision else "passthrough_to_inventory"
        if got == row["expected_intent"]:
            correct += 1
    accuracy = correct / total
    assert accuracy >= 0.85, f"intent accuracy {accuracy:.2%} below 0.85 floor"


def test_high_risk_rows_must_be_perfect(labeled_rows: list[dict]) -> None:
    risky = [r for r in labeled_rows if r.get("risk_level") in {"high", "critical"}]
    if not risky:
        pytest.skip("no high/critical rows to enforce")
    failures = []
    for row in risky:
        decision = classify_polite_boundary(row["question"])
        got_risk = decision.risk_level if decision else "low"
        got_intent = decision.boundary_type if decision else "passthrough_to_inventory"
        if got_risk != row["risk_level"] or got_intent != row["expected_intent"]:
            failures.append(
                {
                    "id": row.get("id"),
                    "question": row["question"],
                    "expected_risk": row["risk_level"],
                    "got_risk": got_risk,
                    "expected_intent": row["expected_intent"],
                    "got_intent": got_intent,
                }
            )
    assert not failures, f"high/critical rows misrouted: {failures}"
