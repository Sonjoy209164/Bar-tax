from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.schemas import InventorySearchFilters
from app.inventory.conversation_state import ConversationState
from app.inventory.ontology import ProductOntology, normalize_inventory_text


COLOR_TERMS = (
    "black",
    "blue",
    "brown",
    "gold",
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
    "হলুদ",
)

OCCASION_TERMS = (
    "anniversary",
    "birthday",
    "biye",
    "biya",
    "boishakh",
    "casual",
    "date",
    "eid",
    "festival",
    "gift",
    "haldi",
    "marriage",
    "office",
    "party",
    "puja",
    "reception",
    "wedding",
    "বিয়ে",
    "বিয়ে",
    "ঈদ",
    "জন্মদিন",
    "পার্টি",
    "অফিস",
)

SIZE_TERMS = (
    "xs",
    "s",
    "m",
    "l",
    "xl",
    "xxl",
    "free size",
    "size",
    "সাইজ",
    "মাপ",
)

SUPPORT_TERMS = (
    "cod",
    "delivery",
    "exchange",
    "order",
    "payment",
    "refund",
    "return",
    "shipping",
    "track",
    "ডেলিভারি",
    "অর্ডার",
    "রিফান্ড",
)

SAFETY_TERMS = (
    "case",
    "doctor",
    "legal",
    "medicine",
    "rash",
    "suicide",
    "lawyer",
    "আইনি",
    "ডাক্তার",
    "মেডিসিন",
)

FACT_FOLLOWUP_TERMS = (
    "available",
    "availability",
    "ache",
    "ase",
    "dam",
    "er dam",
    "koto",
    "price",
    "stock",
    "tell me more",
    "details",
    "দাম",
    "কত",
    "স্টক",
    "আছে",
)

REFERENCE_TERMS = (
    "eta",
    "etar",
    "eita",
    "eitar",
    "first one",
    "second one",
    "third one",
    "it",
    "this",
    "this one",
    "that",
    "that one",
    "এটা",
    "এটার",
    "ওটা",
    "ওটার",
    "প্রথম",
    "দ্বিতীয়",
    "তৃতীয়",
)

ALTERNATIVE_TERMS = (
    "same design",
    "same color",
    "same colour",
    "another color",
    "other color",
    "onno color",
    "ar ki color",
    "aro color",
    "similar",
    "cheaper",
    "matching",
    "sathe matching",
    "go with",
    "what goes with",
    "একই ডিজাইন",
    "এই ডিজাইন",
    "অন্য রঙ",
    "অন্য কালার",
    "আর কালার",
)

BUDGET_PATTERN = re.compile(
    r"(?:under|below|less than|within|moddhe|er moddhe|budget|৳|tk|taka|bdt)\s*[\d,]+|[\d,]+\s*(?:er moddhe|moddhe|tk|taka|bdt|৳)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FlowDecision:
    action: str
    reason: str
    active_category_key: str | None = None
    confidence: float = 0.0


def decide_flow(
    *,
    question: str,
    state: ConversationState,
    ontology: ProductOntology | None = None,
) -> FlowDecision:
    ontology = ontology or ProductOntology()
    active_category = _active_category(state)
    if is_safety_text(question):
        return FlowDecision("SAFETY_ROUTE", "safety text must not continue shopping flow", active_category, 1.0)

    if is_support_text(question):
        return FlowDecision("SUPPORT_ROUTE", "support text must not continue shopping flow", active_category, 1.0)

    if question_mentions_product(question, ontology=ontology):
        return FlowDecision("START_NEW_FLOW", "question mentions a fresh product/category", active_category, 1.0)

    if not active_category:
        return FlowDecision("NO_FLOW", "no active category in conversation state")

    if _has_product_focus(state) and is_compare_or_similar_followup(question):
        return FlowDecision(
            "COMPARE_OR_SIMILAR",
            "alternative, variant, or cross-sell follow-up uses current product focus",
            active_category,
            0.9,
        )

    if is_slot_update(question, ontology=ontology):
        return FlowDecision("UPDATE_FLOW_SLOTS", "slot-only update continues active shopping flow", active_category, 0.92)

    if _has_product_focus(state) and is_product_fact_followup(question):
        return FlowDecision(
            "CONTINUE_PRODUCT_FOCUS",
            "product fact follow-up uses current product focus",
            active_category,
            0.88,
        )

    return FlowDecision("NO_FLOW", "question is not a slot-only shopping continuation", active_category, 0.0)


def is_slot_update(question: str, ontology: ProductOntology | None = None) -> bool:
    ontology = ontology or ProductOntology()
    text = normalize_inventory_text(question)
    raw = question.casefold()
    if not text and not raw.strip():
        return False
    if is_support_or_safety_text(question):
        return False
    if question_mentions_product(question, ontology=ontology):
        return False
    return any(
        (
            _has_any(text, raw, COLOR_TERMS),
            _has_any(text, raw, OCCASION_TERMS),
            _has_any(text, raw, SIZE_TERMS),
            bool(BUDGET_PATTERN.search(raw)),
        )
    )


def is_support_or_safety_text(question: str) -> bool:
    return is_support_text(question) or is_safety_text(question)


def is_support_text(question: str) -> bool:
    text = normalize_inventory_text(question)
    raw = question.casefold()
    return _has_any(text, raw, SUPPORT_TERMS)


def is_safety_text(question: str) -> bool:
    text = normalize_inventory_text(question)
    raw = question.casefold()
    return _has_any(text, raw, SAFETY_TERMS)


def is_product_fact_followup(question: str) -> bool:
    text = normalize_inventory_text(question)
    raw = question.casefold()
    if not text and not raw.strip():
        return False
    return _has_any(text, raw, FACT_FOLLOWUP_TERMS) or _has_any(text, raw, REFERENCE_TERMS)


def is_compare_or_similar_followup(question: str) -> bool:
    text = normalize_inventory_text(question)
    raw = question.casefold()
    if not text and not raw.strip():
        return False
    return _has_any(text, raw, ALTERNATIVE_TERMS)


def question_mentions_product(question: str, *, ontology: ProductOntology | None = None) -> bool:
    ontology = ontology or ProductOntology()
    text = normalize_inventory_text(question)
    if not text:
        return False
    return bool(ontology.detect_product_type(text=text))


def filters_for_flow_continuation(
    *,
    base_filters: InventorySearchFilters,
    state: ConversationState,
    ontology: ProductOntology | None = None,
) -> InventorySearchFilters:
    ontology = ontology or ProductOntology()
    filters = base_filters.model_copy(deep=True)
    slots = state.active_slots or {}

    category_key = slots.get("category_key")
    if isinstance(category_key, str) and category_key and not filters.categories:
        category_label = ontology.DEFAULT_CATEGORY_BY_TYPE.get(category_key)
        if category_label:
            filters.categories = [category_label]

    budget_max = slots.get("budget_max")
    if isinstance(budget_max, (int, float)) and budget_max > 0 and filters.max_price is None:
        filters.max_price = float(budget_max)

    if filters.min_stock is None:
        filters.min_stock = 1

    return filters


def _active_category(state: ConversationState) -> str | None:
    category = (state.active_slots or {}).get("category_key")
    return category if isinstance(category, str) and category else None


def _has_product_focus(state: ConversationState) -> bool:
    return bool(state.last_primary_product_id or state.last_shown_product_ids)


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
