"""
The thinking layer.

Sits ABOVE the existing pipeline. Before the bot extracts slots, retrieves
candidates, reasons over them, and writes an answer — the planner reads the
whole conversation and writes a *plan*: what is this person actually
shopping for, where are we in the conversation, and what should we do next.

The pipeline still does the heavy lifting. The planner just makes sure the
pipeline is operating on a thoughtful interpretation of the situation, not
just the literal text of the latest message.

What it sees:
  - The current question
  - The last 6 turns of conversation (both user + assistant)
  - The ConversationState (last shown products, prior intents, failure count,
    color/occasion/budget signals)
  - The customer's profile if a phone is linked

What it produces (IntentPlan):
  - intent              — the actual intent, may differ from naive classifier
  - customer_situation  — one-paragraph narrative of what's going on
  - key_constraints     — budget, occasion, color, fabric, etc. inferred
                          from the WHOLE conversation, not just this turn
  - should_clarify      — true if even the planner can't tell what to do
  - clarifying_question — what to ask if should_clarify
  - pipeline_hints      — extra signals for downstream layers
  - confidence          — how sure the planner is
  - reasoning           — short trace ("customer rejected bright colors
                          on turn 2, so I'm narrowing to muted palette")

When NOT to invoke (cost-saving heuristic):
  - First turn of a brand-new session with a simple question (intent
    classifier handles those fine — no need for ~3s extra latency)
  - Pure policy / order intents detected with high confidence by the
    cheap regex layer (delivery koto, order korte chai, etc.)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434"
_OLLAMA_MODEL = "qwen3:8b"
_OLLAMA_TIMEOUT = 14.0
_MAX_HISTORY_TURNS = 6


@dataclass(frozen=True)
class IntentPlan:
    intent: str = "unknown"
    customer_situation: str = ""
    key_constraints: dict[str, Any] = field(default_factory=dict)
    should_clarify: bool = False
    clarifying_question: str | None = None
    pipeline_hints: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reasoning: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


_PROMPT = """\
You are the planning brain for a Bangladeshi boutique chatbot. You read the
conversation so far and write a STRUCTURED PLAN that downstream layers
will use. You are not writing the answer. You are deciding what the bot
should actually do for this customer.

Your job:
  1. Figure out what the customer is REALLY shopping for, taking the whole
     conversation into account — not just the last message.
  2. Notice when the customer's need has shifted from earlier turns (e.g.
     they started looking for sarees but now want a panjabi for husband).
  3. Notice when the customer rejected something earlier — never recommend
     it again unless they bring it up.
  4. Track inferred constraints (budget hints, occasion, color preferences,
     people they're shopping for) across turns, even if not explicit this
     turn.
  5. If even with the whole context you genuinely cannot tell, set
     should_clarify=true and write the most useful single question to ask.

Output ONLY a single JSON object — no preamble, no markdown.

JSON schema:
{
  "intent": <one of: fashion_search, fashion_compare, fashion_styling_advice,
            fashion_variant_color, fashion_size_availability,
            fashion_accessory_match, policy_delivery, policy_payment,
            policy_refund, policy_exchange, order_place, order_status,
            order_cancel, smalltalk, unknown>,
  "customer_situation": "<one short paragraph: who they are shopping for,
                          for what occasion, what they have rejected, what
                          they seem to want. write in English.>",
  "key_constraints": {
    "budget_max": <number or null>,
    "occasion": <string or null>,
    "color_preference": <string or null>,
    "fabric_preference": <string or null>,
    "rejected_attributes": [<string>, ...]   // things customer said no to
  },
  "should_clarify": <true | false>,
  "clarifying_question": <string or null — only when should_clarify=true>,
  "pipeline_hints": {
    "shifted_topic": <true | false>,            // did the customer pivot?
    "needs_human_judgement": <true | false>,    // styling / "what suits me?"
    "search_lean": <"strict" | "broad">         // strict slot match vs flexible
  },
  "confidence": <number 0.0–1.0>,
  "reasoning": "<one short sentence on how you decided this>"
}

If the customer wrote in Bangla, the clarifying_question (if any) must be
in Bangla. If Banglish, Banglish. If English, English. The
customer_situation and reasoning are always in English (they are for
internal use by other layers).

{context_block}
Latest customer message: {question}

Output:"""


def plan(
    *,
    question: str,
    conversation_history: list[tuple[str, str]] | None = None,
    state_summary: str | None = None,
    profile_summary: str | None = None,
    ollama_url: str = _OLLAMA_URL,
    model: str = _OLLAMA_MODEL,
    timeout: float = _OLLAMA_TIMEOUT,
) -> IntentPlan | None:
    """
    Run the planner. Returns IntentPlan or None on any failure.
    Caller must handle None gracefully — pipeline runs without plan hints.
    """
    if not question.strip():
        return None

    context_block = _render_context(
        conversation_history=conversation_history,
        state_summary=state_summary,
        profile_summary=profile_summary,
    )

    prompt = (
        _PROMPT.replace("{context_block}", context_block)
               .replace("{question}", question)
    )

    try:
        resp = httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.15, "num_predict": 380},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw_text = resp.json().get("response", "").strip()
    except Exception as exc:
        logger.debug("IntentPlanner HTTP failure: %s", exc)
        return None

    parsed = _parse_json_lenient(raw_text)
    if not isinstance(parsed, dict):
        logger.debug("IntentPlanner non-dict output: %r", raw_text[:200])
        return None

    return _build_plan(parsed)


def should_invoke_planner(
    *,
    question: str,
    conversation_history: list[tuple[str, str]] | None,
    consecutive_failures: int = 0,
) -> bool:
    """
    Cost-saving heuristic. Skip the planner for clearly simple cases:
      - first turn of a brand-new session AND a short question
      - obvious policy / order one-liners
    Invoke whenever there's conversation context to reason over, or the
    bot has been failing the customer.
    """
    if consecutive_failures >= 1:
        return True

    if conversation_history and len([t for t in conversation_history if t[0] == "user"]) >= 1:
        # 2nd turn or later — the conversation has a story to read
        return True

    # First turn — only invoke for non-trivial questions
    text = question.strip().lower()
    if len(text) < 25:
        return False

    # Correction / re-thinking signals — even on turn 1, worth planning
    correction_signals = (
        "actually", "wait", "no", "instead", "rather", "kintu",
        "but", "ektu", "shorry", "sorry", "অপেক্ষা", "আসলে",
    )
    if any(sig in text for sig in correction_signals):
        return True

    # Multi-constraint signals — when the customer is asking for several
    # things at once, the planner adds value over a flat slot extraction
    if text.count(" and ") + text.count(" with ") + text.count(" + ") >= 1:
        return True

    return False


def render_state_summary(conv_state: Any) -> str:
    """Helper for callers — turn a ConversationState into a short bullet list."""
    if conv_state is None:
        return ""
    parts: list[str] = []
    if getattr(conv_state, "last_shown_product_ids", None):
        ids = list(conv_state.last_shown_product_ids)[:5]
        parts.append(f"- last shown products: {', '.join(ids)}")
    if getattr(conv_state, "last_intent", None):
        parts.append(f"- last intent: {conv_state.last_intent}")
    if getattr(conv_state, "color_counts", None):
        top = sorted(conv_state.color_counts.items(), key=lambda kv: -kv[1])[:3]
        parts.append(f"- color signals: {', '.join(f'{c}({n})' for c, n in top)}")
    if getattr(conv_state, "occasion_counts", None):
        top = sorted(conv_state.occasion_counts.items(), key=lambda kv: -kv[1])[:3]
        parts.append(f"- occasion signals: {', '.join(f'{c}({n})' for c, n in top)}")
    if getattr(conv_state, "budget_observations", None):
        budgets = list(conv_state.budget_observations)[-3:]
        if budgets:
            parts.append(f"- budgets mentioned: {budgets}")
    if getattr(conv_state, "consecutive_failures", 0):
        parts.append(f"- bot failed {conv_state.consecutive_failures} times in a row recently")
    return "\n".join(parts)


def render_profile_summary(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    parts: list[str] = []
    if profile.get("favorite_colors"):
        parts.append(f"- known favourite colours: {', '.join(profile['favorite_colors'][:3])}")
    if profile.get("preferred_categories"):
        parts.append(f"- preferred categories: {', '.join(profile['preferred_categories'][:3])}")
    if profile.get("typical_budget"):
        parts.append(f"- typical budget: BDT {profile['typical_budget']:,.0f}")
    if profile.get("preferred_occasion"):
        parts.append(f"- preferred occasion: {profile['preferred_occasion']}")
    return "\n".join(parts)


# ── internals ────────────────────────────────────────────────────────────────

def _render_context(
    *,
    conversation_history: list[tuple[str, str]] | None,
    state_summary: str | None,
    profile_summary: str | None,
) -> str:
    sections: list[str] = []

    if profile_summary:
        sections.append(f"Customer profile (from prior sessions):\n{profile_summary}\n")

    if state_summary:
        sections.append(f"Conversation state so far:\n{state_summary}\n")

    if conversation_history:
        recent = list(conversation_history)[-_MAX_HISTORY_TURNS:]
        lines: list[str] = []
        for role, content in recent:
            who = "Customer" if role == "user" else "Bot"
            lines.append(f"{who}: {content}")
        sections.append("Conversation so far:\n" + "\n".join(lines) + "\n")

    return "\n".join(sections)


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


_VALID_INTENTS = {
    "fashion_search", "fashion_compare", "fashion_styling_advice",
    "fashion_variant_color", "fashion_size_availability",
    "fashion_accessory_match", "fashion_multi_brand_clarification",
    "policy_delivery", "policy_payment", "policy_refund", "policy_exchange",
    "order_place", "order_status", "order_cancel", "smalltalk", "unknown",
}


def _build_plan(payload: dict[str, Any]) -> IntentPlan:
    intent = str(payload.get("intent") or "unknown")
    if intent not in _VALID_INTENTS:
        intent = "unknown"

    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.0

    constraints = payload.get("key_constraints") or {}
    if not isinstance(constraints, dict):
        constraints = {}
    # Sanitise constraint keys we expect
    clean_constraints: dict[str, Any] = {}
    for key in ("budget_max", "occasion", "color_preference", "fabric_preference"):
        v = constraints.get(key)
        if v is not None and v != "":
            clean_constraints[key] = v
    rej = constraints.get("rejected_attributes") or []
    if isinstance(rej, list):
        clean_rej = [str(x) for x in rej if x][:6]
        if clean_rej:
            clean_constraints["rejected_attributes"] = clean_rej

    hints_raw = payload.get("pipeline_hints") or {}
    if not isinstance(hints_raw, dict):
        hints_raw = {}
    hints: dict[str, Any] = {
        "shifted_topic": bool(hints_raw.get("shifted_topic", False)),
        "needs_human_judgement": bool(hints_raw.get("needs_human_judgement", False)),
        "search_lean": str(hints_raw.get("search_lean") or "broad").lower(),
    }
    if hints["search_lean"] not in {"strict", "broad"}:
        hints["search_lean"] = "broad"

    should_clarify = bool(payload.get("should_clarify", False))
    cq = payload.get("clarifying_question")
    cq_str = str(cq).strip() if cq else None
    if should_clarify and not cq_str:
        # Planner said clarify but didn't write a question — don't honour it
        should_clarify = False

    return IntentPlan(
        intent=intent,
        customer_situation=str(payload.get("customer_situation") or "").strip(),
        key_constraints=clean_constraints,
        should_clarify=should_clarify,
        clarifying_question=cq_str if should_clarify else None,
        pipeline_hints=hints,
        confidence=confidence,
        reasoning=str(payload.get("reasoning") or "").strip(),
        raw=payload,
    )
