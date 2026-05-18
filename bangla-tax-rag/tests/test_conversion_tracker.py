"""Tests for the conversion funnel tracker."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.inventory import conversion_tracker


@pytest.fixture
def isolated_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "conversions.jsonl"
    monkeypatch.setattr(conversion_tracker, "_LOG_PATH", p)
    return p


# ── recording ────────────────────────────────────────────────────────────────

def test_record_shown_writes_log(isolated_log: Path) -> None:
    conversion_tracker.record_shown(
        session_id="s1", question="red saree", product_ids=["p1", "p2"],
        intent="fashion_search", confidence=0.9,
    )
    assert isolated_log.exists()
    line = isolated_log.read_text().strip()
    obj = json.loads(line)
    assert obj["event"] == "shown"
    assert obj["product_ids"] == ["p1", "p2"]


def test_record_abstain_writes_reason(isolated_log: Path) -> None:
    conversion_tracker.record_abstain(
        session_id="s1", question="x", intent="fashion_search", reason="no match",
    )
    obj = json.loads(isolated_log.read_text().strip())
    assert obj["event"] == "abstain"
    assert obj["reason"] == "no match"


def test_record_ordered_writes_order_id(isolated_log: Path) -> None:
    conversion_tracker.record_ordered(
        session_id="s1", order_id="ORD-123", product_ids=["p1"], total_amount=5000.0,
    )
    obj = json.loads(isolated_log.read_text().strip())
    assert obj["event"] == "ordered"
    assert obj["order_id"] == "ORD-123"


# ── summarize_conversions ────────────────────────────────────────────────────

def test_empty_summary_when_no_log(isolated_log: Path) -> None:
    s = conversion_tracker.summarize_conversions()
    assert s["shown_total"] == 0
    assert s["conversion_rate"] is None


def test_summary_counts_events(isolated_log: Path) -> None:
    for _ in range(3):
        conversion_tracker.record_shown(
            session_id="s1", question="?", product_ids=["p1"],
            intent="fashion_search", confidence=0.9,
        )
    conversion_tracker.record_abstain(
        session_id="s2", question="?", intent="unknown", reason="x"
    )
    conversion_tracker.record_ordered(session_id="s1", order_id="O1", product_ids=["p1"])

    s = conversion_tracker.summarize_conversions(days=30)
    assert s["shown_total"] == 3
    assert s["abstain_total"] == 1
    assert s["ordered_total"] == 1


def test_top_shown_products(isolated_log: Path) -> None:
    conversion_tracker.record_shown(session_id="s1", question="?",
        product_ids=["p1", "p2"], intent="fashion_search", confidence=0.9)
    conversion_tracker.record_shown(session_id="s2", question="?",
        product_ids=["p1"], intent="fashion_search", confidence=0.9)
    s = conversion_tracker.summarize_conversions(days=30)
    top = dict(s["top_shown_products"])
    assert top.get("p1") == 2
    assert top.get("p2") == 1


def test_drop_off_includes_high_attention_low_conversion(isolated_log: Path) -> None:
    # p1 shown in 4 sessions, ordered in 1
    for sid in ("s1", "s2", "s3", "s4"):
        conversion_tracker.record_shown(
            session_id=sid, question="?", product_ids=["p1"],
            intent="fashion_search", confidence=0.9,
        )
    conversion_tracker.record_ordered(session_id="s1", order_id="O1", product_ids=["p1"])

    s = conversion_tracker.summarize_conversions(days=30)
    drop = s["drop_off_products"]
    assert any(d["product_id"] == "p1" and d["session_conversion_ratio"] < 0.5 for d in drop)


def test_failed_questions_in_summary(isolated_log: Path) -> None:
    conversion_tracker.record_abstain(
        session_id="s1", question="will it match my old saree?",
        intent="fashion_styling_advice", reason="no styling rules"
    )
    s = conversion_tracker.summarize_conversions(days=30)
    failed = s["failed_questions_sample"]
    assert any("will it match" in f["question"] for f in failed)
