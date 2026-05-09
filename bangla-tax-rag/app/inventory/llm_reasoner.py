"""
LLM-as-reasoner over candidate products.

Takes a small set of candidate products (typically the top-N from the
semantic matcher) plus the customer's question, and asks the LLM to:

  1. Pick the best match(es) — usually 1–3 product_ids.
  2. Give a one-line "why this one" reason.
  3. Honestly say "none of these fit" if that's true.
  4. Score its confidence in [0, 1].

This replaces the rigid slot-filter ranker for the open-ended fashion_search
intent. Specific intents (variant_color, size_availability) keep their
deterministic handlers because they have hard correctness rules.

Failure mode: returns None. Caller must have a fallback ranker (the
existing slot filter is fine).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.schemas import InventoryItemRecord

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434"
_OLLAMA_MODEL = "qwen3:8b"
_OLLAMA_TIMEOUT = 14.0  # tighter than answer gen — this is a structured pick
_MAX_CANDIDATES = 8


@dataclass(frozen=True)
class ReasonedSelection:
    selected_product_ids: list[str] = field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0
    none_fit: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


_PROMPT = """\
You help a Bangladeshi boutique recommend products to a customer.

Below are candidate products and the customer's question. Your job is to
choose the best match(es) and explain why in ONE short sentence.

Rules:
- Use ONLY the candidate products listed. Never invent products.
- If NONE of the candidates fit the customer's actual need, say so honestly
  (set "none_fit": true and an empty selected list).
- Prefer fewer, better matches over a long list. 1–3 is ideal.
- Match BOTH the explicit slots (color, fabric, size) AND the implicit
  intent (occasion vibe, customer preferences from prior turns).
- If the customer asked in Bangla or Banglish, write the reasoning in
  the same language. English question → English reasoning.

Return ONLY a single JSON object — no preamble, no markdown.

JSON schema:
{
  "selected_product_ids": [<product_id>, ...],
  "reasoning": "<one short sentence — why these>",
  "confidence": <number between 0.0 and 1.0>,
  "none_fit": <true | false>
}

Customer question: {question}
{context_block}
Candidates:
{candidates}

Output:"""


def reason_over_candidates(
    *,
    question: str,
    candidates: list[InventoryItemRecord],
    customer_context: str | None = None,
    ollama_url: str = _OLLAMA_URL,
    model: str = _OLLAMA_MODEL,
    timeout: float = _OLLAMA_TIMEOUT,
) -> ReasonedSelection | None:
    """
    Ask the LLM to pick from `candidates`. Returns ReasonedSelection or None
    on any failure (HTTP, parse, empty model output).
    """
    if not candidates:
        return ReasonedSelection(
            selected_product_ids=[], reasoning="No candidates.", confidence=0.0, none_fit=True
        )

    candidate_block = _render_candidates(candidates[:_MAX_CANDIDATES])
    context_block = ""
    if customer_context:
        context_block = f"\nCustomer context:\n{customer_context}\n"

    prompt = (
        _PROMPT
        .replace("{question}", question)
        .replace("{context_block}", context_block)
        .replace("{candidates}", candidate_block)
    )

    try:
        resp = httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 220},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw_text = resp.json().get("response", "").strip()
    except Exception as exc:
        logger.debug("LLM reasoner HTTP failure: %s", exc)
        return None

    parsed = _parse_json_lenient(raw_text)
    if not isinstance(parsed, dict):
        logger.debug("LLM reasoner non-dict output: %r", raw_text[:200])
        return None

    return _build_selection(parsed, valid_ids={c.product_id for c in candidates})


def _render_candidates(items: list[InventoryItemRecord]) -> str:
    """Render candidates as numbered, attribute-rich lines."""
    lines: list[str] = []
    for i, item in enumerate(items, 1):
        attrs = item.attributes or {}
        attr_parts = []
        for key in ("color", "fabric", "occasion", "work_type", "size", "brand"):
            v = attrs.get(key)
            if v:
                attr_parts.append(f"{key}={v}")
        attr_str = " | ".join(attr_parts) or "—"
        price = f"BDT {item.price:,.0f}" if item.price else "Price N/A"
        stock = f"stock={item.stock}"
        lines.append(
            f"{i}. id={item.product_id} | name={item.name} | {price} | {stock} | {attr_str}"
        )
    return "\n".join(lines)


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


def _build_selection(payload: dict[str, Any], valid_ids: set[str]) -> ReasonedSelection:
    raw_ids = payload.get("selected_product_ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    selected = [str(x) for x in raw_ids if str(x) in valid_ids][:5]

    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.0

    none_fit = bool(payload.get("none_fit", not selected))
    if not selected:
        none_fit = True

    reasoning = str(payload.get("reasoning") or "").strip()

    return ReasonedSelection(
        selected_product_ids=selected,
        reasoning=reasoning,
        confidence=confidence,
        none_fit=none_fit,
        raw=payload,
    )
