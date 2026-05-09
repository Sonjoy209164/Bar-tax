"""
LLM-first intent classifier and slot extractor.

This is the upgraded path that replaces the regex-first flow:
  Old:  regex extract → if-else intent → optional LLM enrichment
  New:  LLM classify intent + extract all slots + score confidence in ONE call
        regex validates / fills gaps as a safety net

Returns a structured ClassifiedIntent with confidence so the response layer
can decide between answering, asking a clarifying question, or escalating.
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
_OLLAMA_TIMEOUT = 8.0

# Canonical intent vocabulary — must stay aligned with FashionRetailAssistant._classify_intent
_VALID_INTENTS = {
    "fashion_search",
    "fashion_compare",
    "fashion_styling_advice",
    "fashion_variant_color",
    "fashion_size_availability",
    "fashion_accessory_match",
    "fashion_multi_brand_clarification",
    "policy_delivery",
    "policy_payment",
    "policy_refund",
    "policy_exchange",
    "order_place",
    "order_status",
    "order_cancel",
    "smalltalk",
    "unknown",
}

_PROMPT = """\
You classify customer intent for a Bangladeshi fashion boutique chatbot.
The customer may write in Bangla, Banglish (romanized Bangla), English, or mixed.

Return ONLY a single JSON object — no preamble, no markdown fences, no commentary.

Required JSON schema:
{
  "intent": <one of: fashion_search, fashion_compare, fashion_styling_advice,
            fashion_variant_color, fashion_size_availability, fashion_accessory_match,
            fashion_multi_brand_clarification, policy_delivery, policy_payment,
            policy_refund, policy_exchange, order_place, order_status, order_cancel,
            smalltalk, unknown>,
  "category":      <saree | blouse | panjabi | kurti | salwar_kameez | dupatta | shawl |
                    bag | shoes | jewelry | watch | cosmetics | fragrance | null>,
  "color":         <english color name or null>,
  "fabric":        <jamdani | katan | muslin | silk | cotton | georgette | chiffon |
                    linen | denim | velvet | crepe | organza | net | null>,
  "work_type":     <zari | meena | embroidery | block_print | buti | nakshi | printed |
                    plain | hand_woven | banarasi | null>,
  "size":          <string (e.g. "M", "38", "free") or null>,
  "brand":         <brand name string or null>,
  "budget_min":    <number in BDT or null>,
  "budget_max":    <number in BDT or null>,
  "occasion":      <wedding | eid | puja | boishakh | office | casual | birthday |
                    anniversary | party | null>,
  "language":      <"bangla" | "banglish" | "english">,
  "wants_in_stock": <true | false>,
  "confidence":    <number between 0.0 and 1.0 — your certainty about intent + slots>,
  "ambiguity_reason": <short string if confidence < 0.7, else null>
}

Confidence rubric:
  0.9+  intent + at least one concrete slot is unambiguous
  0.7-0.9  intent is clear but slots sparse (e.g. "show me sarees")
  0.5-0.7  multiple intents plausible OR essential slot missing
  <0.5   unclear what the customer wants

Examples:

Input: "লাল জামদানি শাড়ি আছে?"
Output: {"intent":"fashion_search","category":"saree","color":"red","fabric":"jamdani","work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,"occasion":null,"language":"bangla","wants_in_stock":true,"confidence":0.95,"ambiguity_reason":null}

Input: "kichu dekhao"
Output: {"intent":"fashion_search","category":null,"color":null,"fabric":null,"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,"occasion":null,"language":"banglish","wants_in_stock":false,"confidence":0.45,"ambiguity_reason":"customer did not specify category, color, or any concrete slot"}

Input: "jamdani vs katan konta valo?"
Output: {"intent":"fashion_compare","category":"saree","color":null,"fabric":null,"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,"occasion":null,"language":"banglish","wants_in_stock":false,"confidence":0.92,"ambiguity_reason":null}

Input: "Dhaka delivery charge koto?"
Output: {"intent":"policy_delivery","category":null,"color":null,"fabric":null,"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,"occasion":null,"language":"banglish","wants_in_stock":false,"confidence":0.97,"ambiguity_reason":null}

Input: "ei tar same design e blue ache?"
Output: {"intent":"fashion_variant_color","category":null,"color":"blue","fabric":null,"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,"occasion":null,"language":"banglish","wants_in_stock":true,"confidence":0.88,"ambiguity_reason":null}

Input: "order korte chai"
Output: {"intent":"order_place","category":null,"color":null,"fabric":null,"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,"occasion":null,"language":"banglish","wants_in_stock":false,"confidence":0.94,"ambiguity_reason":null}

Input: "thanks"
Output: {"intent":"smalltalk","category":null,"color":null,"fabric":null,"work_type":null,"size":null,"brand":null,"budget_min":null,"budget_max":null,"occasion":null,"language":"english","wants_in_stock":false,"confidence":0.99,"ambiguity_reason":null}

Customer message: {question}
Output:"""


@dataclass(frozen=True)
class ClassifiedIntent:
    """Structured output from the LLM classifier."""
    intent: str = "unknown"
    category: str | None = None
    color: str | None = None
    fabric: str | None = None
    work_type: str | None = None
    size: str | None = None
    brand: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    occasion: str | None = None
    language: str = "english"
    wants_in_stock: bool = False
    confidence: float = 0.0
    ambiguity_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def has_concrete_slot(self) -> bool:
        return any([
            self.category, self.color, self.fabric, self.work_type,
            self.size, self.brand, self.occasion,
            self.budget_max is not None, self.budget_min is not None,
        ])

    @property
    def slot_count(self) -> int:
        return sum(1 for v in (
            self.category, self.color, self.fabric, self.work_type,
            self.size, self.brand, self.occasion,
            self.budget_max, self.budget_min,
        ) if v is not None)


def classify_intent_llm(
    question: str,
    *,
    ollama_url: str = _OLLAMA_URL,
    model: str = _OLLAMA_MODEL,
    timeout: float = _OLLAMA_TIMEOUT,
) -> ClassifiedIntent | None:
    """
    Call Ollama once to get intent + slots + confidence. Returns None on any
    failure — caller should fall back to regex-only path.
    """
    prompt = _PROMPT.replace("{question}", question)
    try:
        resp = httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 280},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw_text = resp.json().get("response", "").strip()
    except Exception as exc:
        logger.debug("LLM intent classification HTTP failure: %s", exc)
        return None

    parsed = _parse_json_lenient(raw_text)
    if not isinstance(parsed, dict):
        logger.debug("LLM intent classifier returned non-dict: %r", raw_text[:200])
        return None
    return _build_classified_intent(parsed)


def _parse_json_lenient(text: str) -> Any:
    """Strip code fences and parse — model often wraps JSON in ```json ... ```."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip("` \n")
    # Find the first { ... } block — sometimes model adds prose after JSON
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _build_classified_intent(payload: dict[str, Any]) -> ClassifiedIntent:
    intent = payload.get("intent") or "unknown"
    if intent not in _VALID_INTENTS:
        intent = "unknown"

    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.0

    def _str(v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s.lower() if s else None

    def _num(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return ClassifiedIntent(
        intent=intent,
        category=_str(payload.get("category")),
        color=_str(payload.get("color")),
        fabric=_str(payload.get("fabric")),
        work_type=_str(payload.get("work_type")),
        size=_str(payload.get("size")),
        brand=_str(payload.get("brand")),
        budget_min=_num(payload.get("budget_min")),
        budget_max=_num(payload.get("budget_max")),
        occasion=_str(payload.get("occasion")),
        language=_str(payload.get("language")) or "english",
        wants_in_stock=bool(payload.get("wants_in_stock", False)),
        confidence=confidence,
        ambiguity_reason=_str(payload.get("ambiguity_reason")),
        raw=payload,
    )
