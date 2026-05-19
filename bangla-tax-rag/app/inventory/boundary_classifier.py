"""
Layer 2 of the conversation entry point: boundary sub-intent classifier.

Architecture:
  user message
    -> safety_rules.match_safety        (regex, deterministic, always first)
    -> is_concrete_shopping_or_support  (let through to inventory pipeline)
    -> classify_with_llm                (Ollama, primary path for sub-intents)
    -> classify_fallback                (keyword backstop for offline / CI)
    -> return None                      (caller asks one clarifying question)

The dataclass `BoundaryDecision` is the new canonical output. The legacy
shim `app/inventory/polite_boundary.py` re-exports it as
`PoliteBoundaryDecision` so existing call sites stay unchanged during the
cutover.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.inventory.boundary_fallback_rules import (
    classify_fallback,
    is_concrete_shopping_or_support,
)
from app.inventory.boundary_text import detect_language, normalize
from app.inventory.boundary_templates import render_template
from app.inventory.safety_rules import match_safety

logger = logging.getLogger(__name__)

_OLLAMA_URL_ENV = "POLITE_BOUNDARY_OLLAMA_URL"
_OLLAMA_MODEL_ENV = "POLITE_BOUNDARY_OLLAMA_MODEL"
_LLM_ENABLED_ENV = "POLITE_BOUNDARY_LLM_ENABLED"

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "qwen3:8b"
_DEFAULT_TIMEOUT = 3.0

# Sub-intents the LLM is allowed to return. Anything else is dropped and the
# fallback runs. Kept aligned with the templates in boundary_templates.yaml.
VALID_SUB_INTENTS: frozenset[str] = frozenset(
    {
        "romantic_off_topic",
        "impression_shopping",
        "gift_recommendation",
        "emotional_low_mood",
        "personal_question_about_bot",
        "joke_chitchat",
        "vague_shopping",
        "unsupported_redirect",
        # Occasion sub-intents are emitted as `occasion_<event>` — handled
        # specially in _coerce_sub_intent below.
    }
)

VALID_OCCASIONS: frozenset[str] = frozenset(
    {
        "wedding",
        "birthday",
        "anniversary",
        "graduation",
        "eid",
        "puja",
        "pohela_boishakh",
        "office",
        "new_job",
        "interview",
        "date",
        "party",
        "travel",
    }
)


@dataclass(frozen=True)
class BoundaryDecision:
    """Final decision returned by the conversation entry layer.

    Shape is stable: the compat shim re-exports this as `PoliteBoundaryDecision`
    so existing call sites (inventory_service, tests) keep working.
    """

    boundary_type: str
    answer: str
    follow_up_question: str | None = None
    confidence: float = 0.85
    language: str = "english"
    risk_level: str = "low"
    allowed_action: str = "playful_redirect"
    handoff_recommended: bool = False
    slots: dict[str, Any] = field(default_factory=dict)
    recommended_categories: tuple[str, ...] = ()
    reasoning: tuple[str, ...] = ()
    source: str = "fallback"  # "safety" | "llm" | "fallback"


def classify_boundary(
    question: str,
    *,
    assistant_mode: str = "support",
    reply_style: str = "short",
) -> BoundaryDecision | None:
    """Decide whether to short-circuit the inventory pipeline with a boundary reply.

    Returns None when the message should flow into the normal inventory search
    (real product/order/business queries).
    """
    text = normalize(question)
    if not text:
        return None
    language = detect_language(question)

    safety = match_safety(text)
    if safety is not None:
        return _build_decision(safety=safety, language=language, source="safety")

    if is_concrete_shopping_or_support(text):
        return None

    intent: dict[str, Any] | None = None
    source = "fallback"
    if _llm_is_enabled():
        intent = classify_with_llm(question)
        if intent is not None:
            source = "llm"
    if intent is None:
        intent = classify_fallback(text)

    if intent is None:
        return None

    return _build_decision(intent=intent, language=language, source=source)


def _build_decision(
    *,
    language: str,
    source: str,
    safety: dict[str, Any] | None = None,
    intent: dict[str, Any] | None = None,
) -> BoundaryDecision:
    payload = safety if safety is not None else intent
    assert payload is not None  # call sites ensure this
    boundary_type = payload.get("boundary_type") or _occasion_to_boundary_type(
        payload.get("sub_intent", "unsupported_redirect"), payload.get("slots", {})
    )
    slots: dict[str, Any] = dict(payload.get("slots", {}))
    no_followup = bool(payload.get("no_followup"))
    answer, follow_up = render_template(
        boundary_type=boundary_type,
        language=language,
        slots=slots,
        categories=tuple(payload.get("recommended_categories", ())),
    )
    if no_followup:
        follow_up = None

    reasoning_value = payload.get("reasoning", ())
    if isinstance(reasoning_value, str):
        reasoning_tuple: tuple[str, ...] = (reasoning_value,)
    else:
        reasoning_tuple = tuple(reasoning_value)

    return BoundaryDecision(
        boundary_type=boundary_type,
        answer=answer,
        follow_up_question=follow_up,
        confidence=float(payload.get("confidence", 0.8)),
        language=language,
        risk_level=str(payload.get("risk_level", "low")),
        allowed_action=str(payload.get("allowed_action", "playful_redirect")),
        handoff_recommended=bool(payload.get("handoff_recommended", False)),
        slots={k: v for k, v in slots.items() if v},
        recommended_categories=tuple(payload.get("recommended_categories", ())),
        reasoning=reasoning_tuple,
        source=source,
    )


def _occasion_to_boundary_type(sub_intent: str, slots: dict[str, Any]) -> str:
    """LLM may return `occasion_wedding` directly OR `occasion` + `slots.occasion`.

    Both paths normalize to `occasion_<event>` so downstream templates resolve.
    """
    if sub_intent.startswith("occasion_"):
        return sub_intent
    if sub_intent == "occasion":
        event = slots.get("occasion")
        if isinstance(event, str) and event in VALID_OCCASIONS:
            return f"occasion_{event}"
    return sub_intent


# ----------------------------------------------------------------------
# LLM path
# ----------------------------------------------------------------------

_LLM_PROMPT = """\
You are the safety + intent router for a Bangladeshi fashion ecommerce bot.
The customer writes in Bangla, Banglish (romanized Bangla), English, or mixed.

The product/order/support queries are ALREADY filtered out before you see
this message. You only receive off-topic, ambiguous, emotional, romantic, or
casual messages. Your job is to classify them into a sub-intent so the bot
can give a warm, brand-safe redirect.

Return ONLY a single JSON object — no preamble, no markdown fences.

JSON schema:
{
  "sub_intent": <one of:
                  romantic_off_topic, impression_shopping, gift_recommendation,
                  emotional_low_mood, personal_question_about_bot,
                  joke_chitchat, vague_shopping, unsupported_redirect,
                  occasion>,
  "occasion": <wedding | birthday | anniversary | graduation | eid | puja |
               pohela_boishakh | office | new_job | interview | date | party |
               travel | null>,
  "recipient": <girlfriend | boyfriend | wife | husband | mother | father |
                friend | sister | brother | someone_special | null>,
  "confidence": <0.0-1.0>,
  "reasoning": <one short sentence explaining the choice>
}

Rules:
  - If a gift intent is present (gift for someone), use "gift_recommendation"
    even when the recipient is a romantic partner. A gift is a real sale.
  - "romantic_off_topic" is for messages directed AT the bot
    ("date me", "tumi amar gf hobe").
  - "occasion" means the user mentions an event with no concrete product
    (wedding, birthday, eid, office, new job, etc.). Fill `occasion`.
  - "emotional_low_mood" is for safe sadness ("mon kharap", "mood off").
    Crisis/self-harm has already been filtered upstream.
  - "vague_shopping" is for "show me something", "what should I buy" with
    no slot.
  - "joke_chitchat" is short small talk ("ki khobor", "tell me a joke").
  - "personal_question_about_bot" is "who are you", "are you human".
  - Use "unsupported_redirect" only when nothing else fits.

Examples:

Input: "amar ekta gf lagbe"
Output: {"sub_intent":"romantic_off_topic","occasion":null,"recipient":null,"confidence":0.92,"reasoning":"User is asking the bot to be their girlfriend"}

Input: "gf er jonno birthday gift chai"
Output: {"sub_intent":"gift_recommendation","occasion":"birthday","recipient":"girlfriend","confidence":0.94,"reasoning":"Real gift purchase for a girlfriend on her birthday"}

Input: "amar biyete jaowa dorkar"
Output: {"sub_intent":"occasion","occasion":"wedding","recipient":null,"confidence":0.9,"reasoning":"User attending a wedding, no concrete product yet"}

Input: "mon kharap"
Output: {"sub_intent":"emotional_low_mood","occasion":null,"recipient":null,"confidence":0.88,"reasoning":"Safe sadness expression, no crisis signal"}

Input: "tumi ki khaiso"
Output: {"sub_intent":"joke_chitchat","occasion":null,"recipient":null,"confidence":0.85,"reasoning":"Casual small talk"}

Input: "tomar boyosh koto"
Output: {"sub_intent":"personal_question_about_bot","occasion":null,"recipient":null,"confidence":0.93,"reasoning":"User asking the bot's age"}

Input: "valo kichu dekhan"
Output: {"sub_intent":"vague_shopping","occasion":null,"recipient":null,"confidence":0.8,"reasoning":"Vague show-me-something with no slot"}

Customer message: {question}
Output:"""


def classify_with_llm(question: str) -> dict[str, Any] | None:
    """Single Ollama call. Returns a fallback-shape intent dict, or None on any failure."""
    prompt = _LLM_PROMPT.replace("{question}", question)
    url = os.environ.get(_OLLAMA_URL_ENV, _DEFAULT_OLLAMA_URL)
    model = os.environ.get(_OLLAMA_MODEL_ENV, _DEFAULT_OLLAMA_MODEL)
    try:
        resp = httpx.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 220},
            },
            timeout=_DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
    except Exception as exc:
        logger.debug("boundary LLM HTTP failure: %s", exc)
        return None

    parsed = _parse_json_lenient(raw)
    if not isinstance(parsed, dict):
        logger.debug("boundary LLM returned non-dict: %r", raw[:200])
        return None

    sub_intent_raw = parsed.get("sub_intent")
    if not isinstance(sub_intent_raw, str):
        return None
    sub_intent = sub_intent_raw.strip()
    occasion = parsed.get("occasion") if isinstance(parsed.get("occasion"), str) else None
    if occasion is not None and occasion not in VALID_OCCASIONS:
        occasion = None
    if sub_intent == "occasion" and occasion is None:
        return None
    if sub_intent != "occasion" and sub_intent not in VALID_SUB_INTENTS:
        return None

    recipient = parsed.get("recipient") if isinstance(parsed.get("recipient"), str) else None
    confidence = parsed.get("confidence", 0.8)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.7
    reasoning = parsed.get("reasoning")
    if not isinstance(reasoning, str):
        reasoning = "LLM boundary classification"

    slots: dict[str, Any] = {}
    if occasion:
        slots["occasion"] = occasion
    if recipient:
        slots["recipient"] = recipient
    if sub_intent == "emotional_low_mood":
        slots.setdefault("mood", "low")

    return {
        "sub_intent": sub_intent,
        "confidence": confidence,
        "allowed_action": _default_action_for(sub_intent),
        "risk_level": "medium" if sub_intent == "emotional_low_mood" else "low",
        "recommended_categories": _categories_for(sub_intent, occasion, recipient),
        "slots": slots,
        "reasoning": reasoning,
    }


def _default_action_for(sub_intent: str) -> str:
    return {
        "romantic_off_topic": "playful_redirect",
        "impression_shopping": "ask_clarifying_question",
        "gift_recommendation": "ask_clarifying_question",
        "emotional_low_mood": "empathetic_soft_product_suggestion",
        "personal_question_about_bot": "short_humor_then_redirect",
        "joke_chitchat": "short_humor_then_redirect",
        "vague_shopping": "ask_clarifying_question",
        "occasion": "occasion_recommendation",
        "unsupported_redirect": "safe_refusal_redirect",
    }.get(sub_intent, "playful_redirect")


def _categories_for(sub_intent: str, occasion: str | None, recipient: str | None) -> tuple[str, ...]:
    # Lazy import to keep boundary_fallback_rules dependency contained.
    from app.inventory.boundary_fallback_rules import EVENT_CATEGORY_MAP, gift_categories

    if sub_intent == "occasion" and occasion:
        return EVENT_CATEGORY_MAP.get(occasion, ("outfit", "gift", "perfume"))
    if sub_intent == "gift_recommendation":
        return gift_categories(recipient=recipient, event=occasion)
    if sub_intent in {"romantic_off_topic", "impression_shopping"}:
        return ("perfume", "outfit", "watch", "gift")
    if sub_intent == "emotional_low_mood":
        return ("self-care", "perfume", "comfortable outfit", "gift")
    if sub_intent == "vague_shopping":
        return ("gift", "outfit", "perfume", "bag", "watch")
    if sub_intent == "personal_question_about_bot":
        return ("products", "gift", "outfit")
    if sub_intent == "joke_chitchat":
        return ("products", "gift", "outfit")
    if sub_intent == "unsupported_redirect":
        return ("gift", "outfit", "perfume")
    return ()


def _parse_json_lenient(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip("` \n")
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


# ----------------------------------------------------------------------
# Toggles (for tests and production safety)
# ----------------------------------------------------------------------

_llm_enabled_override: bool | None = None


def set_llm_enabled(enabled: bool | None) -> None:
    """Programmatic override. Pass None to defer to the env var."""
    global _llm_enabled_override
    _llm_enabled_override = enabled


def _llm_is_enabled() -> bool:
    if _llm_enabled_override is not None:
        return _llm_enabled_override
    raw = os.environ.get(_LLM_ENABLED_ENV, "").strip().casefold()
    return raw in {"1", "true", "yes", "on"}


__all__ = [
    "BoundaryDecision",
    "classify_boundary",
    "classify_with_llm",
    "set_llm_enabled",
    "VALID_SUB_INTENTS",
    "VALID_OCCASIONS",
]
