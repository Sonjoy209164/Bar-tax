"""
Composition layer for the conversation entry point.

`classify_polite_boundary` returns a `BoundaryDecision` whose `answer` field
holds the BASE template (no augmentations). This module turns that base into
a customer-friendly final reply by stacking, in order:

    [memory_ack]  [tone_ack]  base_answer  [catalog_snippet]  [handoff_line]

Each augmentation is independently optional — when a piece is empty or not
applicable, it is omitted with no whitespace artifacts. Detection helpers
(tone, memory ack, catalog picks, handoff) live here so the classifier
stays pure and the service stays thin.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Mapping

import yaml

from app.core.schemas import InventoryItemRecord
from app.inventory.boundary_classifier import BoundaryDecision

_HANDOFF_PATH = Path(__file__).resolve().parents[2] / "config" / "boundary_handoff.yaml"

# Tones the bot reads from the customer message. Templates can supply a
# per-tone ack prefix to match the room.
VALID_TONES: frozenset[str] = frozenset({"neutral", "frustrated", "sad", "excited", "curious"})

# Allowed actions where surfacing real products + handoff is appropriate.
# Crisis / safe-refusal must NOT be padded with shopping content.
_SHOPPABLE_ACTIONS: frozenset[str] = frozenset(
    {
        "playful_redirect",
        "ask_clarifying_question",
        "occasion_recommendation",
        "empathetic_soft_product_suggestion",
        "short_humor_then_redirect",
        "store_support_redirect",
    }
)

# Categories the bot redirects to → catalog terms (category / category_key / tag)
# we'll match against. Map soft synonyms ("self-care", "outfit") to real
# catalog labels so picks always land on something.
_CATEGORY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "outfit": ("saree", "panjabi", "kameez", "kurti", "dress", "shirt"),
    "self-care": ("cosmetics", "perfume", "fragrance", "skin"),
    "comfortable outfit": ("kurti", "kameez", "shirt", "dress"),
    "wellness": ("cosmetics", "perfume", "skin"),
    "products": ("saree", "perfume", "watch", "bag", "jewelry"),
    "gift": ("perfume", "watch", "jewelry", "bag", "cosmetics"),
    "cosmetics": ("cosmetics", "makeup", "skin"),
    "jewelry": ("jewelry", "jewellery", "necklace", "earring", "bangle"),
    "perfume": ("perfume", "fragrance"),
    "watch": ("watch",),
    "bag": ("bag",),
    "saree": ("saree",),
    "panjabi": ("panjabi", "punjabi"),
    "shirt": ("shirt",),
    "pant": ("pant",),
    "shoes": ("shoes", "shoe"),
    "salwar_kameez": ("kameez", "salwar"),
    "wallet": ("wallet",),
    "dress": ("dress",),
}

# Conversation state goes stale fast — past 24h, "earlier you said..." is
# more confusing than helpful.
_MEMORY_TTL_HOURS = 24

# Detector hints. Keep narrow — false positives produce robotic acks.
_FRUSTRATED_HINTS: tuple[str, ...] = (
    "still",
    "again",
    "kobe",
    "kothay",
    "delay",
    "deri",
    "deri kano",
    "valo na",
    "kharap service",
    "khub baje",
    "useless",
    "no response",
    "answer dao",
    "kotha bolo",
    "কবে",
    "কোথায়",
    "দেরি",
    "এখনো",
    "এখনও",
    "খারাপ সার্ভিস",
)

_SAD_HINTS: tuple[str, ...] = (
    "mon kharap",
    "mood off",
    "valo lagche na",
    "bhalo lagche na",
    "sad",
    "depressed",
    "lonely",
    "alone",
    "boring",
    "dukho",
    "মন খারাপ",
    "ভালো লাগছে না",
    "একা",
    "দুঃখ",
)

_EXCITED_HINTS: tuple[str, ...] = (
    "wow",
    "darun",
    "darun lagche",
    "osadharon",
    "asadharon",
    "yes please",
    "love it",
    "perfect",
    "দারুণ",
    "অসাধারণ",
)


@dataclass(frozen=True)
class CatalogPick:
    product_id: str
    sku: str
    name: str
    category: str | None
    price: float | None
    currency: str | None
    stock: int | None


@dataclass(frozen=True)
class PriorContext:
    """Compact snapshot of conversation state used to build the memory ack."""

    recipient: str | None = None
    occasion: str | None = None
    budget_max: float | None = None
    color: str | None = None
    last_intent: str | None = None


@dataclass(frozen=True)
class HandoffHint:
    phone: str
    whatsapp: str | None
    hours: str
    line_by_language: Mapping[str, str]


@dataclass
class EnrichedReply:
    answer: str  # final composed text (memory + tone + base + catalog + handoff)
    follow_up: str | None
    tone: str
    catalog_picks: list[CatalogPick] = field(default_factory=list)
    memory_ack: str | None = None
    handoff_line: str | None = None


# ----------------------------------------------------------------------
# Public entry — service calls this with a fresh BoundaryDecision.
# ----------------------------------------------------------------------

def enrich(
    *,
    decision: BoundaryDecision,
    question: str,
    catalog: Mapping[str, InventoryItemRecord] | None = None,
    prior: PriorContext | None = None,
) -> EnrichedReply:
    """Compose the final user-facing reply from the base decision."""
    language = decision.language
    tone = detect_tone(question)

    memory_ack = build_memory_ack(prior=prior, language=language) if prior else None

    picks: list[CatalogPick] = []
    catalog_snippet = ""
    if catalog and _can_show_products(decision):
        picks = pick_catalog_products(
            catalog=catalog,
            recommended_categories=decision.recommended_categories,
        )
        catalog_snippet = format_catalog_snippet(picks, language=language)

    handoff_line = ""
    if decision.handoff_recommended:
        handoff_line = render_handoff_line(language)

    final = _compose(
        base_answer=decision.answer,
        memory_ack=memory_ack,
        tone_ack=_tone_ack(tone, language),
        catalog_snippet=catalog_snippet,
        handoff_line=handoff_line,
    )
    return EnrichedReply(
        answer=final,
        follow_up=decision.follow_up_question,
        tone=tone,
        catalog_picks=picks,
        memory_ack=memory_ack,
        handoff_line=handoff_line or None,
    )


def _can_show_products(decision: BoundaryDecision) -> bool:
    if not decision.recommended_categories:
        return False
    if decision.allowed_action not in _SHOPPABLE_ACTIONS:
        return False
    if decision.risk_level in {"high", "critical"}:
        return False
    return True


# ----------------------------------------------------------------------
# #3 Tone detection
# ----------------------------------------------------------------------

_CAPS_RUN_RE = re.compile(r"[A-Z]{4,}")


def detect_tone(question: str) -> str:
    text = question or ""
    lowered = text.casefold()
    exclamations = text.count("!")
    question_marks = text.count("?")

    if _has_any_phrase(lowered, _SAD_HINTS):
        return "sad"
    frustrated_signal = (
        _has_any_phrase(lowered, _FRUSTRATED_HINTS)
        or question_marks >= 3
        or bool(_CAPS_RUN_RE.search(text))
    )
    if frustrated_signal:
        return "frustrated"
    if _has_any_phrase(lowered, _EXCITED_HINTS) or exclamations >= 2:
        return "excited"
    if question_marks >= 1 and len(text.split()) <= 6:
        return "curious"
    return "neutral"


def _has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


_TONE_ACKS: dict[str, dict[str, str]] = {
    "frustrated": {
        "english": "I hear you — sorry for the friction.",
        "banglish": "Bujhte parchi — etar jonno sorry.",
        "bangla": "বুঝতে পারছি — এর জন্য দুঃখিত।",
    },
    "sad": {
        "english": "That's not easy.",
        "banglish": "Eta easy na, bujhte parchi.",
        "bangla": "এটা সহজ না, বুঝতে পারছি।",
    },
    "excited": {
        "english": "Love that energy!",
        "banglish": "Darun!",
        "bangla": "দারুণ!",
    },
    "curious": {},  # leave neutral
    "neutral": {},
}


def _tone_ack(tone: str, language: str) -> str:
    per_language = _TONE_ACKS.get(tone, {})
    return per_language.get(language, "")


# ----------------------------------------------------------------------
# #4 Memory ack
# ----------------------------------------------------------------------

def build_prior_context(
    state: Any | None,
    *,
    now: datetime | None = None,
) -> PriorContext | None:
    """Distill a ConversationState into the slots we'd actually reference."""
    if state is None:
        return None
    updated_at = getattr(state, "updated_at", "")
    if not _is_fresh(updated_at, now=now):
        return None
    slots = getattr(state, "active_slots", {}) or {}
    last_intent = getattr(state, "last_intent", None)
    recipient = slots.get("recipient") if isinstance(slots, dict) else None
    occasion = slots.get("occasion") if isinstance(slots, dict) else None
    color = slots.get("color_family") or slots.get("color") if isinstance(slots, dict) else None
    budget_max = slots.get("budget_max") if isinstance(slots, dict) else None
    budget_value = float(budget_max) if isinstance(budget_max, (int, float)) and budget_max > 0 else None

    if not any([recipient, occasion, color, budget_value]):
        return None
    return PriorContext(
        recipient=str(recipient) if recipient else None,
        occasion=str(occasion) if occasion else None,
        budget_max=budget_value,
        color=str(color) if color else None,
        last_intent=str(last_intent) if last_intent else None,
    )


def build_memory_ack(*, prior: PriorContext, language: str) -> str | None:
    parts = []
    if prior.occasion:
        parts.append(f"the {prior.occasion}" if language == "english" else prior.occasion)
    if prior.recipient:
        parts.append(
            f"for your {prior.recipient}" if language == "english" else
            (f"{prior.recipient} er jonno" if language == "banglish" else f"{prior.recipient}-এর জন্য")
        )
    if prior.budget_max:
        bdt = int(prior.budget_max)
        parts.append(
            f"under ৳{bdt}" if language == "english" else
            (f"budget ৳{bdt}" if language == "banglish" else f"৳{bdt} বাজেট")
        )
    if not parts:
        return None
    joined = ", ".join(parts)
    if language == "bangla":
        return f"আগে বলেছিলেন {joined} — সেটা মাথায় রেখে:"
    if language == "banglish":
        return f"Earlier ja bolechilen ({joined}) — sheta mathay rekhe:"
    return f"Earlier you mentioned {joined} — keeping that in mind:"


def _is_fresh(updated_at: str, *, now: datetime | None) -> bool:
    if not updated_at:
        return True  # fresh state from in-memory store has no timestamp yet
    try:
        ts = datetime.fromisoformat(updated_at)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return reference - ts <= timedelta(hours=_MEMORY_TTL_HOURS)


# ----------------------------------------------------------------------
# #1 Catalog-grounded redirects
# ----------------------------------------------------------------------

def pick_catalog_products(
    *,
    catalog: Mapping[str, InventoryItemRecord],
    recommended_categories: tuple[str, ...],
    n: int = 3,
) -> list[CatalogPick]:
    """Pick up to n in-stock products matching any recommended category."""
    if not catalog or not recommended_categories:
        return []

    search_terms = _expand_categories(recommended_categories)
    if not search_terms:
        return []

    matches: list[tuple[float, CatalogPick]] = []
    for item in catalog.values():
        if item.stock <= 0:
            continue
        if not item.include_in_rag:
            continue
        score = _match_score(item, search_terms)
        if score <= 0:
            continue
        pick = CatalogPick(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            category=item.category,
            price=item.price,
            currency=item.currency,
            stock=item.stock,
        )
        matches.append((score, pick))

    matches.sort(key=lambda x: (-x[0], -(x[1].stock or 0), (x[1].price or 0)))
    return [pick for _, pick in matches[:n]]


def _expand_categories(categories: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for cat in categories:
        if not cat:
            continue
        key = cat.casefold()
        for synonym in _CATEGORY_SYNONYMS.get(key, (key,)):
            s = synonym.casefold()
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def _match_score(item: InventoryItemRecord, search_terms: list[str]) -> float:
    """Cheap weighted scorer — higher = better match for one of the terms."""
    haystacks: list[tuple[float, str]] = []
    if item.category:
        haystacks.append((3.0, item.category.casefold()))
    cat_key = (item.attributes or {}).get("category_key", "")
    if cat_key:
        haystacks.append((3.0, cat_key.casefold()))
    for tag in item.tags or []:
        haystacks.append((1.5, tag.casefold()))
    for v in (item.attributes or {}).values():
        if isinstance(v, str) and v:
            haystacks.append((0.5, v.casefold()))

    score = 0.0
    for term in search_terms:
        for weight, hay in haystacks:
            if term == hay:
                score += weight * 2
            elif term in hay:
                score += weight
    return score


def format_catalog_snippet(picks: list[CatalogPick], *, language: str) -> str:
    if not picks:
        return ""
    lines = [_format_pick_line(p, language=language) for p in picks]
    if language == "bangla":
        intro = "যেমন:"
    elif language == "banglish":
        intro = "Jemon:"
    else:
        intro = "For example:"
    return intro + " " + "; ".join(lines) + "."


def _format_pick_line(pick: CatalogPick, *, language: str) -> str:
    price = ""
    if pick.price is not None:
        currency = pick.currency or "BDT"
        symbol = "৳" if currency.upper() == "BDT" else f"{currency} "
        price = f" — {symbol}{int(pick.price) if float(pick.price).is_integer() else pick.price:g}"
    return f"{pick.name}{price}"


# ----------------------------------------------------------------------
# #5 Graceful handoff
# ----------------------------------------------------------------------

_handoff_cache: HandoffHint | None = None
_handoff_lock = Lock()


def _load_handoff() -> HandoffHint | None:
    global _handoff_cache
    if _handoff_cache is not None:
        return _handoff_cache
    with _handoff_lock:
        if _handoff_cache is not None:
            return _handoff_cache
        try:
            with _HANDOFF_PATH.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            return None
        block = (data or {}).get("handoff", {}) or {}
        if not block.get("enabled", False):
            return None
        channels = block.get("channels", {}) or {}
        per_language = block.get("per_language", {}) or {}
        _handoff_cache = HandoffHint(
            phone=str(channels.get("phone", "")),
            whatsapp=str(channels.get("whatsapp")) if channels.get("whatsapp") else None,
            hours=str(channels.get("hours", "")),
            line_by_language={
                str(k): str(v) for k, v in per_language.items() if isinstance(v, str)
            },
        )
        return _handoff_cache


def reload_handoff() -> None:
    global _handoff_cache
    with _handoff_lock:
        _handoff_cache = None


def render_handoff_line(language: str) -> str:
    hint = _load_handoff()
    if hint is None:
        return ""
    template = hint.line_by_language.get(language) or hint.line_by_language.get("english", "")
    if not template:
        return ""
    return template.format(
        phone=hint.phone,
        whatsapp=hint.whatsapp or hint.phone,
        hours=hint.hours,
    )


# ----------------------------------------------------------------------
# Composer
# ----------------------------------------------------------------------

def _compose(
    *,
    base_answer: str,
    memory_ack: str | None,
    tone_ack: str,
    catalog_snippet: str,
    handoff_line: str,
) -> str:
    parts: list[str] = []
    if memory_ack:
        parts.append(memory_ack)
    if tone_ack:
        parts.append(tone_ack)
    if base_answer:
        parts.append(base_answer)
    if catalog_snippet:
        parts.append(catalog_snippet)
    if handoff_line:
        parts.append(handoff_line)
    return " ".join(p.strip() for p in parts if p and p.strip())


__all__ = [
    "CatalogPick",
    "EnrichedReply",
    "HandoffHint",
    "PriorContext",
    "build_memory_ack",
    "build_prior_context",
    "detect_tone",
    "enrich",
    "format_catalog_snippet",
    "pick_catalog_products",
    "reload_handoff",
    "render_handoff_line",
]
