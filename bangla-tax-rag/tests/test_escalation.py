"""Tests for the escalation / human-handoff module."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.inventory.conversation_state import ConversationState
from app.inventory import escalation


@pytest.fixture
def isolated_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the notifications log to a per-test tmp file."""
    p = tmp_path / "escalations.jsonl"
    monkeypatch.setattr(escalation, "_NOTIFICATIONS_PATH", p)
    return p


# ── decide_escalation ────────────────────────────────────────────────────────

def test_no_escalation_for_fresh_session() -> None:
    s = ConversationState(session_id="x")
    d = escalation.decide_escalation(state=s, question="red saree achhe?")
    assert d.should_escalate is False


def test_escalation_after_three_failures() -> None:
    s = ConversationState(session_id="x", consecutive_failures=3)
    d = escalation.decide_escalation(state=s, question="ki ache?")
    assert d.should_escalate is True
    assert "consecutive_failures" in (d.reason or "")
    assert d.message is not None


def test_no_escalation_at_two_failures() -> None:
    s = ConversationState(session_id="x", consecutive_failures=2)
    d = escalation.decide_escalation(state=s, question="ki ache?")
    assert d.should_escalate is False


def test_explicit_human_request_escalates_immediately() -> None:
    s = ConversationState(session_id="x", consecutive_failures=0)
    d = escalation.decide_escalation(state=s, question="I want to talk to a human please")
    assert d.should_escalate is True
    assert d.reason == "explicit_request"


def test_bangla_human_request_escalates() -> None:
    s = ConversationState(session_id="x")
    d = escalation.decide_escalation(state=s, question="মানুষের সাথে কথা বলব")
    assert d.should_escalate is True
    assert d.reason == "explicit_request"


def test_thumbs_down_threshold_escalates() -> None:
    s = ConversationState(session_id="x", last_thumbs_down_count=2)
    d = escalation.decide_escalation(state=s, question="ami chai")
    assert d.should_escalate is True
    assert "thumbs_down" in (d.reason or "")


# ── emit_escalation_notification ─────────────────────────────────────────────

def test_emit_writes_log_entry(isolated_log: Path) -> None:
    s = ConversationState(session_id="sess1", consecutive_failures=3, last_question="test?")
    d = escalation.decide_escalation(state=s, question="test?")
    eid = escalation.emit_escalation_notification(state=s, decision=d, last_question="test?")
    assert eid != ""
    assert isolated_log.exists()
    content = isolated_log.read_text()
    assert "sess1" in content
    assert eid in content


def test_emit_skips_when_decision_is_negative(isolated_log: Path) -> None:
    s = ConversationState(session_id="x")
    d = escalation.EscalationDecision(should_escalate=False)
    eid = escalation.emit_escalation_notification(state=s, decision=d)
    assert eid == ""
    assert not isolated_log.exists()


# ── list_pending_escalations + mark_resolved ─────────────────────────────────

def test_list_pending(isolated_log: Path) -> None:
    s = ConversationState(session_id="sess1", consecutive_failures=3)
    d = escalation.decide_escalation(state=s, question="?")
    escalation.emit_escalation_notification(state=s, decision=d)
    pending = escalation.list_pending_escalations()
    assert len(pending) == 1
    assert pending[0]["session_id"] == "sess1"
    assert pending[0]["status"] == "pending"


def test_mark_resolved(isolated_log: Path) -> None:
    s = ConversationState(session_id="sess1", consecutive_failures=3)
    d = escalation.decide_escalation(state=s, question="?")
    eid = escalation.emit_escalation_notification(state=s, decision=d)
    ok = escalation.mark_escalation_resolved(eid)
    assert ok is True
    pending = escalation.list_pending_escalations()
    assert pending == []


def test_mark_resolved_for_unknown_id_returns_false(isolated_log: Path) -> None:
    s = ConversationState(session_id="sess1", consecutive_failures=3)
    d = escalation.decide_escalation(state=s, question="?")
    escalation.emit_escalation_notification(state=s, decision=d)
    assert escalation.mark_escalation_resolved("ESC-DOES-NOT-EXIST") is False
