"""
Runtime feature flags for the boutique bot's LLM layers.

Every intelligent layer (LLM slot extraction, semantic matching, LLM
reasoner, answer critic, soft-confirm, escalation, conversion tracking)
can be turned off via an environment variable without redeploying. This
matters because:

  - If the LLM reasoner starts misbehaving in production, you should be
    able to disable it in seconds, not after a code review.
  - If Ollama is overloaded, you can disable the critic to halve LLM
    calls per request.
  - For benchmarking and A/B testing, you need to compare with/without
    each layer cleanly.

All flags default to ON. Set the env var to "0", "false", or "off" to
disable.

Env vars:
  BOT_ENABLE_LLM_INTENT      — LLM-first intent classifier
  BOT_ENABLE_LLM_REASONER    — LLM picks best candidate(s)
  BOT_ENABLE_ANSWER_CRITIC   — Self-critique + regenerate
  BOT_ENABLE_SEMANTIC_MATCHER — Embedding-based catalog fallback
  BOT_ENABLE_NATURAL_ANSWER  — Ollama natural language answer gen
  BOT_ENABLE_SOFT_CONFIRM    — Medium-confidence confirmation tail
  BOT_ENABLE_ESCALATION      — Human handoff signaling
  BOT_ENABLE_PREFERENCE_LEARNING — Implicit profile updates
  BOT_ENABLE_CONVERSION_TRACKING — Funnel telemetry
"""
from __future__ import annotations

import os

_FALSY = {"0", "false", "off", "no", ""}


def _flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSY


def llm_intent_enabled() -> bool:
    return _flag("BOT_ENABLE_LLM_INTENT")


def llm_reasoner_enabled() -> bool:
    return _flag("BOT_ENABLE_LLM_REASONER")


def answer_critic_enabled() -> bool:
    return _flag("BOT_ENABLE_ANSWER_CRITIC")


def semantic_matcher_enabled() -> bool:
    return _flag("BOT_ENABLE_SEMANTIC_MATCHER")


def natural_answer_enabled() -> bool:
    return _flag("BOT_ENABLE_NATURAL_ANSWER")


def soft_confirm_enabled() -> bool:
    return _flag("BOT_ENABLE_SOFT_CONFIRM")


def escalation_enabled() -> bool:
    return _flag("BOT_ENABLE_ESCALATION")


def preference_learning_enabled() -> bool:
    return _flag("BOT_ENABLE_PREFERENCE_LEARNING")


def conversion_tracking_enabled() -> bool:
    return _flag("BOT_ENABLE_CONVERSION_TRACKING")


def snapshot() -> dict[str, bool]:
    """Return current state of every flag — for /owner/health diagnostics."""
    return {
        "llm_intent": llm_intent_enabled(),
        "llm_reasoner": llm_reasoner_enabled(),
        "answer_critic": answer_critic_enabled(),
        "semantic_matcher": semantic_matcher_enabled(),
        "natural_answer": natural_answer_enabled(),
        "soft_confirm": soft_confirm_enabled(),
        "escalation": escalation_enabled(),
        "preference_learning": preference_learning_enabled(),
        "conversion_tracking": conversion_tracking_enabled(),
    }
