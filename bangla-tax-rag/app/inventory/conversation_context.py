from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.schemas import (
    InventoryAnswerPlan,
    InventoryAskRequest,
    InventoryConversationTurn,
    InventorySearchFilters,
)
from app.inventory.conversation_state import ConversationState
from app.inventory.conversation_flow import (
    decide_flow,
    filters_for_flow_continuation,
)
from app.inventory.coreference_resolver import resolve_coreference
from app.inventory.memory_policy import (
    product_focus_expired,
    question_has_product_mention,
    should_use_product_focus,
)
from app.inventory.ontology import ProductOntology, normalize_inventory_text


_FOLLOW_UP_TERMS = (
    "eta",
    "eita",
    "etar",
    "eitar",
    "ei ta",
    "ota",
    "oita",
    "otar",
    "oi ta",
    "seta",
    "shetar",
    "tar",
    "er dam",
    "dam",
    "price",
    "koto",
    "size",
    "m size",
    "l size",
    "xl",
    "stock",
    "available",
    "ache",
    "ase",
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
    "kom dam",
    "budget",
    "first one",
    "second one",
    "third one",
    "last one",
    "it",
    "tell me more",
    "more about it",
    "show similar",
    "similar",
    "matching",
    "sathe matching",
    "go with",
    "what goes with",
    "this",
    "this one",
    "that",
    "that one",
    "order this",
    "nibo",
    "cart",
    "এটা",
    "এটার",
    "ওটা",
    "ওটার",
    "সেটা",
    "সেটার",
    "এর দাম",
    "দাম",
    "কত",
    "সাইজ",
    "মাপ",
    "স্টক",
    "আছে",
    "একই ডিজাইন",
    "এই ডিজাইন",
    "অন্য রঙ",
    "অন্য কালার",
    "আর কালার",
    "প্রথম",
    "দ্বিতীয়",
    "তৃতীয়",
    "শেষ",
)

_NEW_REQUEST_TERMS = (
    "show me",
    "show",
    "find",
    "find me",
    "list",
    "search",
    "recommend",
    "suggest",
    "dekhao",
    "dekhaw",
    "dekhate",
    "lagbe",
    "chai",
    "chahi",
    "need",
    "want",
    "do you have",
    "have any",
    "ache",
    "ase",
    "দেখাও",
    "লাগবে",
    "চাই",
    "আছে",
)


@dataclass(frozen=True)
class ConversationHydration:
    request: InventoryAskRequest
    used_state: bool
    reason: str | None = None


def hydrate_request_from_state(
    *,
    request: InventoryAskRequest,
    state: ConversationState,
    ontology: ProductOntology | None = None,
) -> ConversationHydration:
    """Inject server-side conversation state into a request safely.

    The browser may forget to send `focused_product_ids`, `active_filters`, or
    the previous answer plan. This helper reconstructs those from SQLite state
    so follow-up turns still work after refreshes, image replies, and polite
    boundary detours.
    """

    if not request.session_id or not state.session_id or state.turn_count <= 0:
        return ConversationHydration(request=request, used_state=False)

    ontology = ontology or ProductOntology()
    is_followup = question_looks_like_followup(request.question)
    is_new_request = question_looks_like_new_request(request.question, ontology)
    focus_policy = should_use_product_focus(
        question=request.question,
        state=state,
        ontology=ontology,
    )
    flow_decision = decide_flow(
        question=request.question,
        state=state,
        ontology=ontology,
    )
    updates: dict[str, Any] = {}
    reasons: list[str] = []

    context_turn = build_context_turn(state)
    if context_turn is not None and not _history_already_has_context(request.conversation_history):
        updates["conversation_history"] = [context_turn, *request.conversation_history]
        reasons.append("prepended_recent_state_context")

    summary = build_state_summary(state)
    if summary and not request.conversation_summary:
        updates["conversation_summary"] = summary
        reasons.append("attached_state_summary")

    if focus_policy.expired:
        if request.focused_product_ids:
            updates["focused_product_ids"] = []
        if request.last_answer_plan is not None:
            updates["last_answer_plan"] = None
        reasons.append("ignored_expired_product_focus")

    if flow_decision.action == "UPDATE_FLOW_SLOTS":
        flow_filters = filters_for_flow_continuation(
            base_filters=request.filters,
            state=state,
            ontology=ontology,
        )
        if flow_filters != request.filters:
            updates["filters"] = flow_filters
            reasons.append("continued_active_shopping_flow")
        if request.last_answer_plan is None and (
            state.last_primary_product_id or state.last_shown_product_ids
        ):
            updates["last_answer_plan"] = build_answer_plan_from_state(state)
            reasons.append("restored_flow_answer_plan")

    if is_followup and not is_new_request and focus_policy.allowed:
        if not request.focused_product_ids and state.last_shown_product_ids:
            coref = resolve_coreference(
                question=request.question,
                last_shown_product_ids=state.last_shown_product_ids,
                last_primary_product_id=state.last_primary_product_id,
            )
            if coref.resolved_product_id:
                updates["focused_product_ids"] = [coref.resolved_product_id]
                reasons.append(f"resolved_coreference:{coref.resolution_type}")
            else:
                updates["focused_product_ids"] = list(state.last_shown_product_ids)
                reasons.append("restored_last_shown_products")

        if request.last_answer_plan is None and (
            state.last_primary_product_id or state.last_shown_product_ids
        ):
            updates["last_answer_plan"] = build_answer_plan_from_state(state)
            reasons.append("restored_last_answer_plan")

    if request.active_filters is None:
        filters = build_active_filters_from_state(state, ontology=ontology)
        if filters is not None:
            updates["active_filters"] = filters
            reasons.append("restored_active_filters")

    if not updates:
        return ConversationHydration(request=request, used_state=False)

    return ConversationHydration(
        request=request.model_copy(update=updates, deep=True),
        used_state=True,
        reason=", ".join(reasons),
    )


def question_looks_like_followup(question: str) -> bool:
    text = normalize_inventory_text(question)
    if not text and not question.strip():
        return False
    return _has_any_followup_phrase(text, question.casefold(), _FOLLOW_UP_TERMS)


def question_looks_like_new_request(question: str, ontology: ProductOntology | None = None) -> bool:
    ontology = ontology or ProductOntology()
    text = normalize_inventory_text(question)
    if not text:
        return False
    if question_has_direct_anchor_reference(question):
        return False
    return question_has_product_mention(question, ontology=ontology)


def question_has_direct_anchor_reference(question: str) -> bool:
    text = normalize_inventory_text(question)
    raw = question.casefold()
    return _has_any_followup_phrase(
        text,
        raw,
        (
            "eta",
            "eita",
            "etar",
            "eitar",
            "ei ta",
            "this",
            "this one",
            "that",
            "that one",
            "it",
            "এটা",
            "এটার",
            "এটি",
            "এটির",
            "এইটা",
            "এইটার",
            "ওটা",
            "ওটার",
            "সেটা",
            "সেটার",
        ),
    )


def _has_any_followup_phrase(text: str, raw: str, phrases: tuple[str, ...]) -> bool:
    for phrase in phrases:
        normalized = normalize_inventory_text(phrase)
        if normalized:
            pattern = re.escape(normalized).replace(r"\ ", r"\s+")
            if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text):
                return True
        if _has_bangla(phrase) and phrase in raw:
            return True
    return False


def _has_bangla(text: str) -> bool:
    return any("\u0980" <= char <= "\u09ff" for char in text)


def build_answer_plan_from_state(state: ConversationState) -> InventoryAnswerPlan:
    if product_focus_expired(state):
        return InventoryAnswerPlan(
            intent="conversation_memory",
            strategy="server_conversation_memory_expired",
            reasoning_steps=["Prior product focus expired and was not restored."],
        )
    shown = list(state.last_shown_product_ids)
    primary = state.last_primary_product_id or (shown[0] if shown else None)
    alternatives = [pid for pid in shown if pid != primary]
    return InventoryAnswerPlan(
        intent=state.last_intent or "conversation_memory",
        detected_intent=state.last_intent,
        strategy="server_conversation_memory",
        primary_product_id=primary,
        alternative_product_ids=alternatives,
        preferences=dict(state.active_slots),
        reasoning_steps=["Restored prior answer plan from server conversation state."],
    )


def build_active_filters_from_state(
    state: ConversationState,
    *,
    ontology: ProductOntology | None = None,
) -> InventorySearchFilters | None:
    ontology = ontology or ProductOntology()
    slots = state.active_slots or {}
    filters = InventorySearchFilters()

    category_key = slots.get("category_key")
    if isinstance(category_key, str) and category_key:
        category_label = ontology.DEFAULT_CATEGORY_BY_TYPE.get(category_key)
        if category_label:
            filters.categories = [category_label]

    budget_max = slots.get("budget_max")
    if not isinstance(budget_max, (int, float)) and state.budget_observations:
        budget_max = state.budget_observations[-1]
    if isinstance(budget_max, (int, float)) and budget_max > 0:
        filters.max_price = float(budget_max)

    if not any((filters.categories, filters.max_price is not None)):
        return None
    return filters


def build_context_turn(state: ConversationState) -> InventoryConversationTurn | None:
    summary = build_state_summary(state)
    if not summary:
        return None
    return InventoryConversationTurn(role="user", content=f"[Recent chat context: {summary}]")


def build_state_summary(state: ConversationState) -> str | None:
    parts: list[str] = []
    if state.last_intent:
        parts.append(f"last intent={state.last_intent}")
    focus_is_fresh = not product_focus_expired(state)
    if focus_is_fresh and state.last_primary_product_id:
        parts.append(f"focused product={state.last_primary_product_id}")
    if focus_is_fresh and state.last_shown_product_ids:
        shown = ", ".join(state.last_shown_product_ids[:5])
        parts.append(f"shown products={shown}")
    slot_text = _format_slots(state.active_slots)
    if slot_text:
        parts.append(f"active preferences={slot_text}")
    if state.budget_observations:
        parts.append(f"last budget<=BDT {state.budget_observations[-1]:,.0f}")
    if state.color_counts:
        color = max(state.color_counts, key=state.color_counts.get)
        parts.append(f"frequent color={color}")
    if state.occasion_counts:
        occasion = max(state.occasion_counts, key=state.occasion_counts.get)
        parts.append(f"frequent occasion={occasion}")
    return "; ".join(parts) if parts else None


def _format_slots(slots: dict[str, Any]) -> str:
    allowed = (
        "category_key",
        "color",
        "color_family",
        "size",
        "budget_max",
        "occasion",
        "fabric",
        "design_id",
        "variant_group_id",
    )
    parts = []
    for key in allowed:
        value = slots.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value[:4])
        parts.append(f"{key}={value}")
    return ", ".join(parts)


def _history_already_has_context(history: list[InventoryConversationTurn]) -> bool:
    return any(turn.content.startswith("[Recent chat context:") for turn in history)
