"""Tests for the top-of-pipeline IntentPlanner."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.inventory.intent_planner import (
    IntentPlan,
    _build_plan,
    _parse_json_lenient,
    plan as plan_intent,
    render_profile_summary,
    render_state_summary,
    should_invoke_planner,
)


# ── should_invoke_planner heuristic ──────────────────────────────────────────

def test_skips_simple_first_turn_question() -> None:
    assert should_invoke_planner(
        question="red saree?",
        conversation_history=None,
        consecutive_failures=0,
    ) is False


def test_invokes_when_history_exists() -> None:
    assert should_invoke_planner(
        question="another one?",
        conversation_history=[("user", "saree dekhao"), ("assistant", "...")],
        consecutive_failures=0,
    ) is True


def test_invokes_after_consecutive_failures() -> None:
    assert should_invoke_planner(
        question="x",
        conversation_history=None,
        consecutive_failures=2,
    ) is True


def test_invokes_on_correction_signal_first_turn() -> None:
    assert should_invoke_planner(
        question="actually I think I want something for puja instead",
        conversation_history=None,
        consecutive_failures=0,
    ) is True


def test_invokes_on_multi_constraint_first_turn() -> None:
    assert should_invoke_planner(
        question="red jamdani saree with gold work and a matching blouse",
        conversation_history=None,
        consecutive_failures=0,
    ) is True


# ── _parse_json_lenient ──────────────────────────────────────────────────────

def test_parses_clean_json() -> None:
    out = _parse_json_lenient('{"intent":"fashion_search","confidence":0.9}')
    assert out["intent"] == "fashion_search"


def test_parses_json_with_code_fence() -> None:
    out = _parse_json_lenient('```json\n{"intent":"fashion_search"}\n```')
    assert out["intent"] == "fashion_search"


def test_parses_json_with_prose() -> None:
    out = _parse_json_lenient('Sure thing. {"intent":"fashion_search"} done.')
    assert out["intent"] == "fashion_search"


def test_returns_none_on_garbage() -> None:
    assert _parse_json_lenient("nope") is None


# ── _build_plan ──────────────────────────────────────────────────────────────

def test_build_plan_normalizes_intent() -> None:
    p = _build_plan({"intent": "bogus_intent", "confidence": 0.8})
    assert p.intent == "unknown"


def test_build_plan_clamps_confidence() -> None:
    p = _build_plan({"intent": "fashion_search", "confidence": 1.5})
    assert p.confidence == 1.0


def test_build_plan_extracts_constraints() -> None:
    p = _build_plan({
        "intent": "fashion_search",
        "key_constraints": {
            "budget_max": 5000,
            "occasion": "wedding",
            "rejected_attributes": ["bright colors", "synthetic"],
        },
        "confidence": 0.85,
    })
    assert p.key_constraints["budget_max"] == 5000
    assert p.key_constraints["occasion"] == "wedding"
    assert p.key_constraints["rejected_attributes"] == ["bright colors", "synthetic"]


def test_build_plan_clarify_without_question_is_dropped() -> None:
    """If planner says clarify but didn't write a question, don't honour it."""
    p = _build_plan({
        "intent": "fashion_search",
        "should_clarify": True,
        "clarifying_question": "",
        "confidence": 0.5,
    })
    assert p.should_clarify is False


def test_build_plan_clarify_with_question_is_honoured() -> None:
    p = _build_plan({
        "intent": "fashion_search",
        "should_clarify": True,
        "clarifying_question": "কোন অনুষ্ঠানের জন্য?",
        "confidence": 0.5,
    })
    assert p.should_clarify is True
    assert p.clarifying_question == "কোন অনুষ্ঠানের জন্য?"


def test_build_plan_validates_search_lean() -> None:
    p = _build_plan({
        "intent": "fashion_search",
        "pipeline_hints": {"search_lean": "weird_value"},
        "confidence": 0.8,
    })
    assert p.pipeline_hints["search_lean"] == "broad"


# ── plan() — mocked HTTP ─────────────────────────────────────────────────────

def test_plan_returns_intent_plan_on_success() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": (
            '{"intent":"fashion_search",'
            '"customer_situation":"Customer is shopping for a wedding gift, '
            'budget tight, prefers traditional sarees.",'
            '"key_constraints":{"budget_max":5000,"occasion":"wedding",'
            '"rejected_attributes":["bright colors"]},'
            '"should_clarify":false,'
            '"clarifying_question":null,'
            '"pipeline_hints":{"shifted_topic":false,"needs_human_judgement":true,'
            '"search_lean":"broad"},'
            '"confidence":0.88,'
            '"reasoning":"customer rejected bright on turn 2"}'
        )
    }
    with patch("httpx.post", return_value=mock_resp):
        p = plan_intent(question="kichu suggest koro")
    assert p is not None
    assert p.intent == "fashion_search"
    assert "wedding gift" in p.customer_situation
    assert p.key_constraints["budget_max"] == 5000
    assert p.pipeline_hints["needs_human_judgement"] is True
    assert p.confidence == 0.88


def test_plan_returns_clarify_when_planner_decides() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "response": (
            '{"intent":"fashion_search",'
            '"customer_situation":"Customer mentioned occasion but not budget or color.",'
            '"key_constraints":{},"should_clarify":true,'
            '"clarifying_question":"কোন রঙ পছন্দ?",'
            '"pipeline_hints":{},"confidence":0.45,"reasoning":"too vague"}'
        )
    }
    with patch("httpx.post", return_value=mock_resp):
        p = plan_intent(question="?", conversation_history=[("user", "kichu dekhao")])
    assert p.should_clarify is True
    assert p.clarifying_question == "কোন রঙ পছন্দ?"


def test_plan_returns_none_on_http_error() -> None:
    with patch("httpx.post", side_effect=ConnectionError("refused")):
        p = plan_intent(question="x", conversation_history=[("user", "y")])
    assert p is None


def test_plan_returns_none_on_invalid_json() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"response": "not json at all"}
    with patch("httpx.post", return_value=mock_resp):
        p = plan_intent(question="x", conversation_history=[("user", "y")])
    assert p is None


def test_plan_returns_none_for_empty_question() -> None:
    p = plan_intent(question="   ", conversation_history=[])
    assert p is None


def test_plan_passes_history_and_state_into_prompt() -> None:
    captured: dict = {}

    def capture(url, **kw):
        captured["json"] = kw.get("json", {})
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": '{"intent":"fashion_search","customer_situation":"x","key_constraints":{},"should_clarify":false,"clarifying_question":null,"pipeline_hints":{},"confidence":0.7,"reasoning":"x"}'
        }
        return resp

    with patch("httpx.post", side_effect=capture):
        plan_intent(
            question="now what?",
            conversation_history=[("user", "saree dekhao"), ("assistant", "lal dekhalam")],
            state_summary="- last shown: p1, p2\n- color signals: red(2)",
            profile_summary="- known favourite colours: red, gold",
        )
    prompt = captured["json"]["prompt"]
    assert "saree dekhao" in prompt
    assert "lal dekhalam" in prompt
    assert "color signals: red(2)" in prompt
    assert "favourite colours: red, gold" in prompt


# ── render helpers ───────────────────────────────────────────────────────────

def test_render_state_summary_handles_none() -> None:
    assert render_state_summary(None) == ""


def test_render_state_summary_with_signals() -> None:
    state = MagicMock()
    state.last_shown_product_ids = ["p1", "p2"]
    state.last_intent = "fashion_search"
    state.color_counts = {"red": 3, "blue": 1}
    state.occasion_counts = {"wedding": 2}
    state.budget_observations = [4500, 5000]
    state.consecutive_failures = 0
    summary = render_state_summary(state)
    assert "p1" in summary
    assert "fashion_search" in summary
    assert "red(3)" in summary


def test_render_profile_summary_empty() -> None:
    assert render_profile_summary(None) == ""
    assert render_profile_summary({}) == ""


def test_render_profile_summary_with_data() -> None:
    profile = {
        "favorite_colors": ["red", "gold"],
        "preferred_categories": ["saree"],
        "typical_budget": 6000,
    }
    summary = render_profile_summary(profile)
    assert "red, gold" in summary
    assert "saree" in summary
    assert "6,000" in summary
