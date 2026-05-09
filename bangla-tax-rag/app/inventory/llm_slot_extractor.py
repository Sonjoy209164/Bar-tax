from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
Extract structured shopping intent from a customer message.
Return ONLY a valid JSON object — no explanation, no markdown.

JSON schema:
{
  "category": string | null,        // saree, panjabi, kurti, bag, shoe, jewelry, cosmetics, fragrance, watch, accessories
  "color": string | null,           // English color name (e.g., "red", "navy", "white")
  "fabric": string | null,          // jamdani, katan, muslin, silk, cotton, georgette, chiffon, linen
  "work_type": string | null,       // zari, meena, embroidery, block_print, buti, printed, plain
  "size": string | null,            // e.g., "M", "42", "free"
  "brand": string | null,           // e.g., "Aarong"
  "budget_max": number | null,      // maximum price in BDT
  "budget_min": number | null,      // minimum price in BDT
  "occasion": string | null,        // wedding, eid, office, casual, boishakh, birthday
  "intent": string,                 // one of: fashion_search, fashion_compare, fashion_styling_advice, fashion_variant_color, fashion_size_availability, fashion_accessory_match, policy_delivery, policy_payment, policy_refund, order_place, order_status
  "language": string,               // bangla, banglish, english
  "wants_in_stock": boolean         // true if customer explicitly wants in-stock items only
}

Examples:
Input: "লাল জামদানি শাড়ি আছে?"
Output: {"category":"saree","color":"red","fabric":"jamdani","work_type":null,"size":null,"brand":null,"budget_max":null,"budget_min":null,"occasion":null,"intent":"fashion_search","language":"bangla","wants_in_stock":true}

Input: "jamdani vs katan konta nibo?"
Output: {"category":"saree","color":null,"fabric":null,"work_type":null,"size":null,"brand":null,"budget_max":null,"budget_min":null,"occasion":null,"intent":"fashion_compare","language":"banglish","wants_in_stock":false}

Input: "Dhaka delivery charge koto?"
Output: {"category":null,"color":null,"fabric":null,"work_type":null,"size":null,"brand":null,"budget_max":null,"budget_min":null,"occasion":null,"intent":"policy_delivery","language":"banglish","wants_in_stock":false}

Customer message: {question}
Output:"""


def extract_slots_via_llm(
    question: str,
    ollama_url: str = "http://localhost:11434",
    model: str = "qwen3:8b",
    timeout: float = 8.0,
) -> dict[str, Any] | None:
    """
    Call Ollama to extract structured slots from a customer question.
    Returns parsed dict or None on any failure (caller should fall back to regex).
    Fast timeout (8s) so it never blocks the main response path.
    """
    try:
        import httpx  # already a project dependency
        prompt = _EXTRACTION_PROMPT.replace("{question}", question)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 200},
        }
        resp = httpx.post(f"{ollama_url}/api/generate", json=payload, timeout=timeout)
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        # Strip markdown code fence if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        slots = json.loads(raw)
        if not isinstance(slots, dict):
            return None
        return slots
    except Exception as exc:
        logger.debug("LLM slot extraction failed (falling back to regex): %s", exc)
        return None


def merge_llm_slots_into_fashion_slots(
    llm_slots: dict[str, Any],
    regex_slots: Any,
) -> Any:
    """
    Merge LLM-extracted slots into regex-extracted FashionRetailSlots.
    LLM wins on fields where regex returned None; regex wins otherwise
    (regex is more reliable for structured patterns like phone numbers).
    """
    if llm_slots is None:
        return regex_slots

    from app.inventory.fashion_retail import FashionRetailSlots  # lazy import

    def _pick(llm_val: Any, regex_val: Any) -> Any:
        return regex_val if regex_val is not None else llm_val

    return FashionRetailSlots(
        category_key=_pick(llm_slots.get("category"), regex_slots.category_key),
        category_label=regex_slots.category_label,
        color=_pick(llm_slots.get("color"), regex_slots.color),
        color_family=regex_slots.color_family,
        size=_pick(llm_slots.get("size"), regex_slots.size),
        budget_min=_pick(llm_slots.get("budget_min"), regex_slots.budget_min),
        budget_max=_pick(llm_slots.get("budget_max"), regex_slots.budget_max),
        fabric=_pick(llm_slots.get("fabric"), regex_slots.fabric),
        work_type=_pick(llm_slots.get("work_type"), regex_slots.work_type),
        occasion=_pick(llm_slots.get("occasion"), regex_slots.occasion),
        style=regex_slots.style,
        design_id=regex_slots.design_id,
        wants_in_stock=regex_slots.wants_in_stock or bool(llm_slots.get("wants_in_stock")),
        intent=_pick(llm_slots.get("intent"), regex_slots.intent),
        language=_pick(llm_slots.get("language"), regex_slots.language),
        evidence=regex_slots.evidence + (("llm_extraction",),) if llm_slots else regex_slots.evidence,
    )


# In-process cache for the availability probe — same request typically
# checks 3+ times (intent classifier, reasoner, answer gen, critic).
# Without caching that's 3+ HTTP probes per request even though the
# answer can't change in milliseconds. Cache for 30s so we re-check
# often enough to recover from a flapping Ollama server.
_OLLAMA_PROBE_CACHE: dict[str, tuple[float, bool]] = {}
_OLLAMA_PROBE_TTL_SECONDS = 30.0


def is_ollama_available(url: str = "http://localhost:11434", timeout: float = 1.5) -> bool:
    import time
    now = time.monotonic()
    cached = _OLLAMA_PROBE_CACHE.get(url)
    if cached is not None and (now - cached[0]) < _OLLAMA_PROBE_TTL_SECONDS:
        return cached[1]
    try:
        import httpx
        resp = httpx.get(f"{url}/api/tags", timeout=timeout)
        result = resp.status_code == 200
    except Exception:
        result = False
    _OLLAMA_PROBE_CACHE[url] = (now, result)
    return result


def reset_ollama_probe_cache() -> None:
    """Test/admin helper — clears the availability cache."""
    _OLLAMA_PROBE_CACHE.clear()
