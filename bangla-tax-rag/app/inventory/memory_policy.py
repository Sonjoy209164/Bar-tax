from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.inventory.ontology import ProductOntology, normalize_inventory_text

PRODUCT_FOCUS_TTL_SECONDS = 30 * 60
EXTENDED_PRODUCT_FOCUS_TTL_SECONDS = 60 * 60
SESSION_PREFERENCE_TTL_SECONDS = 7 * 24 * 60 * 60

BLOCKED_MEMORY_INTENTS = {
    "abusive",
    "abusive_mild",
    "abusive_severe",
    "crisis",
    "joke_chitchat",
    "legal_advice",
    "medical_legal",
    "medical_or_health_advice",
    "political",
    "random_tech",
    "romantic_off_topic",
    "self_harm",
    "self_harm_or_crisis",
    "unknown_fallback",
}

COMMERCE_BOUNDARY_INTENTS = {
    "gift_recommendation",
    "occasion_birthday",
    "occasion_wedding",
    "vague_shopping",
}

REFERENCE_TERMS = (
    "eta",
    "etar",
    "eita",
    "eitar",
    "ota",
    "otar",
    "oita",
    "seta",
    "shetar",
    "tar",
    "er dam",
    "this",
    "this one",
    "that",
    "that one",
    "it",
    "first one",
    "second one",
    "third one",
    "last one",
    "same design",
    "same color",
    "same colour",
    "another color",
    "other color",
    "onno color",
    "ar ki color",
    "aro color",
    "order this",
    "compare it",
    "compare that",
    "tell me more",
    "more about it",
    "more about that",
    "show similar",
    "similar",
    "cheaper",
    "matching",
    "sathe matching",
    "go with",
    "what goes with",
    "এটা",
    "এটার",
    "ওটা",
    "ওটার",
    "সেটা",
    "সেটার",
    "তার",
    "এর দাম",
    "প্রথম",
    "দ্বিতীয়",
    "তৃতীয়",
    "শেষ",
    "একই ডিজাইন",
    "এই ডিজাইন",
    "অন্য রঙ",
    "অন্য কালার",
    "আর কালার",
)

FOLLOWUP_FACT_TERMS = (
    "price",
    "dam",
    "koto",
    "size",
    "stock",
    "available",
    "ache",
    "ase",
    "m size",
    "l size",
    "xl",
    "দাম",
    "কত",
    "সাইজ",
    "মাপ",
    "স্টক",
    "আছে",
)

COLOR_TERMS = (
    "black",
    "blue",
    "brown",
    "green",
    "grey",
    "gray",
    "maroon",
    "navy",
    "olive",
    "pink",
    "purple",
    "red",
    "white",
    "yellow",
    "কালো",
    "নীল",
    "লাল",
    "সাদা",
    "সবুজ",
)

PRODUCT_TERMS = (
    "bag",
    "belt",
    "blouse",
    "dress",
    "earring",
    "frock",
    "gift",
    "jewelry",
    "kameez",
    "necklace",
    "panjabi",
    "pant",
    "polo",
    "sandal",
    "saree",
    "shirt",
    "shoe",
    "watch",
    "শাড়ি",
    "সাড়ি",
    "পাঞ্জাবি",
    "স্যান্ডেল",
    "জুতা",
    "ব্লাউজ",
)

NON_PRODUCT_FACT_TOPICS = (
    "age",
    "boyosh",
    "biryani",
    "case",
    "charge",
    "delivery",
    "kacchi",
    "kachchi",
    "legal",
    "order status",
    "where is my order",
    "বয়স",
    "বয়স",
    "বিরিয়ানি",
    "ডেলিভারি",
    "চার্জ",
    "আইনি",
)

NEW_REQUEST_TERMS = (
    "show me",
    "show",
    "find",
    "find me",
    "list",
    "search",
    "recommend",
    "suggest",
    "do you have",
    "have any",
    "ache",
    "ase",
    "dekhao",
    "dekhaw",
    "dekhate",
    "lagbe",
    "chai",
    "need",
    "want",
    "আছে",
    "দেখাও",
    "লাগবে",
    "চাই",
)


@dataclass(frozen=True)
class MemoryPolicyDecision:
    allowed: bool
    reason: str
    source: str | None = None
    confidence: float = 0.0
    expired: bool = False
    age_seconds: int | None = None
    ttl_seconds: int | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def default_product_focus_ttl(intent: str | None = None) -> int:
    normalized = (intent or "").strip().casefold()
    if normalized in {"image_search", "order_flow", "cart_add", "checkout"}:
        return EXTENDED_PRODUCT_FOCUS_TTL_SECONDS
    return PRODUCT_FOCUS_TTL_SECONDS


def product_focus_expires_at(
    *,
    updated_at: str | None,
    ttl_seconds: int | None,
) -> str | None:
    updated = parse_iso_datetime(updated_at)
    if updated is None or not ttl_seconds:
        return None
    return (updated + timedelta(seconds=ttl_seconds)).isoformat()


def product_focus_age_seconds(state: Any, *, now: datetime | None = None) -> int | None:
    updated = parse_iso_datetime(getattr(state, "product_focus_updated_at", None))
    if updated is None:
        return None
    current = now or utc_now()
    return max(0, int((current - updated).total_seconds()))


def product_focus_expired(state: Any, *, now: datetime | None = None) -> bool:
    expires_at = parse_iso_datetime(getattr(state, "product_focus_expires_at", None))
    current = now or utc_now()
    if expires_at is not None:
        return current >= expires_at

    updated = parse_iso_datetime(getattr(state, "product_focus_updated_at", None))
    ttl_seconds = getattr(state, "product_focus_ttl_seconds", None)
    if updated is None or not ttl_seconds:
        return False
    return current >= updated + timedelta(seconds=int(ttl_seconds))


def question_has_reference_language(question: str) -> bool:
    text = normalize_inventory_text(question)
    raw = question.casefold()
    if not text and not raw.strip():
        return False
    if _has_any(text, raw, NON_PRODUCT_FACT_TOPICS):
        return False
    if _has_any(text, raw, REFERENCE_TERMS):
        return True
    if _has_price_followup(text, raw):
        return True
    if _has_size_followup(text, raw):
        return True
    if _has_color_availability_followup(text, raw):
        return True
    if _is_bare_availability_followup(text, raw):
        return True
    return False


def question_has_new_product_request(
    question: str,
    *,
    ontology: ProductOntology | None = None,
) -> bool:
    if not question_has_product_mention(question, ontology=ontology):
        return False
    text = normalize_inventory_text(question)
    raw = question.casefold()
    return _has_any(text, raw, NEW_REQUEST_TERMS)


def question_has_product_mention(
    question: str,
    *,
    ontology: ProductOntology | None = None,
) -> bool:
    ontology = ontology or ProductOntology()
    text = normalize_inventory_text(question)
    raw = question.casefold()
    if not text and not raw.strip():
        return False
    return bool(ontology.detect_product_type(text=text)) or _has_any(
        text,
        raw,
        PRODUCT_TERMS,
    )


def should_use_product_focus(
    *,
    question: str,
    state: Any,
    ontology: ProductOntology | None = None,
    now: datetime | None = None,
) -> MemoryPolicyDecision:
    if not getattr(state, "last_shown_product_ids", None) and not getattr(
        state, "last_primary_product_id", None
    ):
        return MemoryPolicyDecision(False, "no product focus is available")

    age = product_focus_age_seconds(state, now=now)
    ttl = getattr(state, "product_focus_ttl_seconds", None)
    if product_focus_expired(state, now=now):
        return MemoryPolicyDecision(
            False,
            "product focus memory expired",
            source=getattr(state, "product_focus_source", None),
            confidence=float(getattr(state, "product_focus_confidence", 0.0) or 0.0),
            expired=True,
            age_seconds=age,
            ttl_seconds=ttl,
        )

    has_direct_anchor = _has_direct_anchor_reference(question)
    if question_has_product_mention(question, ontology=ontology) and not has_direct_anchor:
        return MemoryPolicyDecision(
            False,
            "current question is a new explicit product/category request",
            source=getattr(state, "product_focus_source", None),
            confidence=float(getattr(state, "product_focus_confidence", 0.0) or 0.0),
            age_seconds=age,
            ttl_seconds=ttl,
        )

    if question_has_new_product_request(question, ontology=ontology) and not has_direct_anchor:
        return MemoryPolicyDecision(
            False,
            "current question is a new explicit product/category request",
            source=getattr(state, "product_focus_source", None),
            confidence=float(getattr(state, "product_focus_confidence", 0.0) or 0.0),
            age_seconds=age,
            ttl_seconds=ttl,
        )

    if not question_has_reference_language(question):
        return MemoryPolicyDecision(
            False,
            "no clear follow-up reference detected",
            source=getattr(state, "product_focus_source", None),
            confidence=float(getattr(state, "product_focus_confidence", 0.0) or 0.0),
            age_seconds=age,
            ttl_seconds=ttl,
        )

    return MemoryPolicyDecision(
        True,
        "clear follow-up reference within product-focus TTL",
        source=getattr(state, "product_focus_source", None),
        confidence=float(getattr(state, "product_focus_confidence", 0.0) or 0.0),
        age_seconds=age,
        ttl_seconds=ttl,
    )


def should_write_memory(
    *,
    intent: str,
    slots: dict[str, Any] | None,
    product_ids: list[str],
    primary_product_id: str | None,
    confidence: float,
    abstained: bool,
) -> MemoryPolicyDecision:
    normalized_intent = (intent or "").strip().casefold()
    risk_level = str((slots or {}).get("risk_level") or "").strip().casefold()
    allowed_action = str((slots or {}).get("allowed_action") or "").strip().casefold()

    if normalized_intent in BLOCKED_MEMORY_INTENTS:
        return MemoryPolicyDecision(False, f"blocked memory write for {normalized_intent}")
    if risk_level in {"high", "critical"}:
        return MemoryPolicyDecision(False, f"blocked memory write for {risk_level}-risk turn")
    if "medical" in normalized_intent or "legal" in normalized_intent or "crisis" in normalized_intent:
        return MemoryPolicyDecision(False, f"blocked sensitive memory write for {normalized_intent}")
    if allowed_action in {"crisis_safe_response", "safe_refusal", "neutral_boundary_redirect"}:
        return MemoryPolicyDecision(False, f"blocked memory write for action {allowed_action}")

    has_product_focus = bool(product_ids or primary_product_id)
    if has_product_focus and (abstained or confidence < 0.5):
        return MemoryPolicyDecision(False, "blocked low-confidence product-focus write")

    if normalized_intent in COMMERCE_BOUNDARY_INTENTS:
        return MemoryPolicyDecision(True, f"allowed commerce boundary memory for {normalized_intent}")

    return MemoryPolicyDecision(True, "allowed commerce memory write")


def filter_safe_slots_for_memory(
    *,
    intent: str,
    slots: dict[str, Any] | None,
) -> dict[str, Any]:
    if not slots:
        return {}
    write_decision = should_write_memory(
        intent=intent,
        slots=slots,
        product_ids=[],
        primary_product_id=None,
        confidence=1.0,
        abstained=False,
    )
    if not write_decision.allowed:
        return {}
    blocked_prefixes = {
        "risk_level",
        "allowed_action",
        "handoff_recommended",
        "polite_boundary_type",
        "tone",
    }
    return {
        key: value
        for key, value in slots.items()
        if value is not None and key not in blocked_prefixes
    }


def _is_variant_followup(question: str) -> bool:
    text = normalize_inventory_text(question)
    raw = question.casefold()
    return _has_any(
        text,
        raw,
        (
            "same design",
            "same color",
            "same colour",
            "another color",
            "other color",
            "onno color",
            "ar ki color",
            "aro color",
            "এই ডিজাইন",
            "একই ডিজাইন",
            "অন্য রঙ",
            "অন্য কালার",
            "আর কালার",
        ),
    )


def _has_direct_anchor_reference(question: str) -> bool:
    text = normalize_inventory_text(question)
    raw = question.casefold()
    return _has_any(
        text,
        raw,
        (
            "eta",
            "etar",
            "eita",
            "this",
            "this one",
            "that",
            "that one",
            "it",
            "go with this",
            "what goes with this",
            "এটা",
            "এটার",
            "এটি",
            "এটির",
            "এর",
        ),
    )


def _has_price_followup(text: str, raw: str) -> bool:
    if _has_any(text, raw, ("delivery", "charge", "order", "boyosh", "age", "ডেলিভারি", "চার্জ", "বয়স", "বয়স")):
        return False
    return _has_any(text, raw, ("price", "dam", "er dam", "দাম"))


def _has_size_followup(text: str, raw: str) -> bool:
    return _has_any(
        text,
        raw,
        ("size", "m size", "l size", "xl", "xxl", "সাইজ", "মাপ", "38", "39", "40", "41", "42"),
    )


def _has_color_availability_followup(text: str, raw: str) -> bool:
    if _has_any(text, raw, PRODUCT_TERMS):
        return False
    has_color = _has_any(text, raw, COLOR_TERMS)
    has_availability = _has_any(
        text,
        raw,
        ("ache", "ase", "available", "stock", "color", "colour", "আছে", "কালার", "রঙ"),
    )
    return has_color and has_availability


def _is_bare_availability_followup(text: str, raw: str) -> bool:
    compact = text.strip()
    raw_compact = " ".join(raw.split())
    return compact in {"ache", "ase", "available", "stock", "stock ache"} or raw_compact in {
        "আছে",
        "স্টক আছে",
    }


def _has_any(text: str, raw: str, phrases: tuple[str, ...]) -> bool:
    for phrase in phrases:
        normalized = normalize_inventory_text(phrase)
        if normalized and _contains_ascii_phrase(text, normalized):
            return True
        if _has_bangla(phrase) and phrase in raw:
            return True
    return False


def _contains_ascii_phrase(text: str, phrase: str) -> bool:
    pattern = re.escape(phrase).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text))


def _has_bangla(text: str) -> bool:
    return any("\u0980" <= char <= "\u09ff" for char in text)
