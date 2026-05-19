"""
Offline fallback for the boundary classifier.

This file exists because:
  - the LLM path (boundary_classifier.classify_with_llm) needs Ollama
  - unit tests and CI run without Ollama
  - production must degrade gracefully when the LLM is unreachable

It is NOT the place to add new sub-intents. New sub-intents should be added
by:
  1. labeling 5-10 real examples in evaluation/offtopic_real_labeled.jsonl
  2. extending the LLM prompt in boundary_classifier.py with the new label
  3. (optionally) extending these tuples if the offline fallback must also
     understand the new label

The detection here is intentionally narrow — it returns a sub-intent only
when the signal is unambiguous. Ambiguous messages return None so the caller
can decide what to do (ask a clarifying question, route to vague_shopping).
"""
from __future__ import annotations

from typing import Any

from app.inventory.boundary_text import has_any, matches_any

EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "wedding": (
        "biye",
        "biya",
        "biyete",
        "wedding",
        "marriage",
        "বিয়ে",
        "বিয়েতে",
    ),
    "birthday": ("birthday", "jonmodin", "জন্মদিন", "বার্থডে"),
    "anniversary": ("anniversary", "barsiki", "বার্ষিকী", "অ্যানিভার্সারি"),
    "graduation": ("graduation", "convocation", "গ্র্যাজুয়েশন", "কনভোকেশন"),
    "eid": ("eid", "ঈদ", "ইদ"),
    "puja": ("puja", "পূজা", "পুজা"),
    "pohela_boishakh": ("pohela boishakh", "boishakh", "পহেলা বৈশাখ", "বৈশাখ"),
    "office": ("office", "অফিস"),
    "new_job": ("new job", "job join", "join korbo", "new office"),
    "interview": ("interview", "ইন্টারভিউ"),
    "date": ("date", "ডেট"),
    "party": ("party", "পার্টি"),
    "travel": ("travel", "tour", "trip", "ghurte", "ঘুরতে", "ভ্রমণ"),
}

EVENT_CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "wedding": ("saree", "panjabi", "shirt", "shoes", "perfume", "bag", "jewelry", "watch", "gift"),
    "birthday": ("gift", "outfit", "perfume", "watch", "bag", "cosmetics"),
    "anniversary": ("gift", "perfume", "watch", "bag", "jewelry", "outfit"),
    "graduation": ("gift", "watch", "perfume", "bag", "outfit"),
    "eid": ("saree", "panjabi", "salwar_kameez", "shoes", "perfume", "bag"),
    "puja": ("saree", "panjabi", "jewelry", "bag", "shoes"),
    "pohela_boishakh": ("saree", "panjabi", "jewelry", "bag", "shoes"),
    "office": ("shirt", "pant", "bag", "shoes", "watch", "perfume"),
    "new_job": ("shirt", "pant", "bag", "shoes", "watch", "perfume"),
    "interview": ("shirt", "pant", "shoes", "watch", "bag"),
    "date": ("outfit", "perfume", "watch", "gift"),
    "party": ("saree", "dress", "shirt", "shoes", "perfume", "bag", "jewelry"),
    "travel": ("bag", "shoes", "comfortable outfit", "watch", "perfume"),
}

GIFT_KEYWORDS: tuple[str, ...] = (
    "gift",
    "gifts",
    "present",
    "upohar",
    "উপহার",
    "গিফট",
    "উপহার দিতে",
    "উপহার চাই",
    "গিফট চাই",
    "gift dite",
    "gift nibo",
)

RELATIONSHIP_KEYWORDS: tuple[str, ...] = (
    "gf",
    "girlfriend",
    "g.f",
    "bf",
    "boyfriend",
    "b.f",
    "prem",
    "valobasha",
    "bhalobasha",
    "bhalobasho",
    "valobasho",
    "bhalobaso",
    "valobaso",
    "love me",
    "love korba",
    "love korben",
    "date me",
    "will you date",
    "date korba",
    "date korben",
    "biye korba",
    "biye korben",
    "marry me",
    "প্রেম",
    "ভালোবাসা",
    "ভালবাসা",
    "ভালোবাসো",
    "ভালবাসো",
    "ভালোবাসেন",
    "ভালবাসেন",
    "ডেট করবেন",
    "বিয়ে করবেন",
)

ROMANTIC_BOUNDARY_PATTERNS: tuple[str, ...] = (
    r"\b(?:amar|amr|আমার)\s+(?:ekta|akta|একটা)?\s*(?:gf|girlfriend|bf|boyfriend)\s+(?:lagbe|chai|dorkar)\b",
    r"\b(?:tumi|apni|আপনি|তুমি)\s+.*(?:prem|date|biye)\s+(?:korba|korben|করবেন|করবা)\b",
    r"\b(?:prem|date)\s+(?:korba|korben|করবেন|করবা)\b",
    r"\bwill\s+you\s+date\s+me\b",
)

IMPRESSION_SHOPPING_KEYWORDS: tuple[str, ...] = (
    "crush",
    "someone special",
    "special person",
    "impress",
    "impress korte",
    "impression",
    "valo impression",
    "bhalo impression",
    "ইমপ্রেস",
    "ইমপ্রেশন",
    "পছন্দ করাতে",
    "পটাতে",
)

RECIPIENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "girlfriend": ("gf", "girlfriend", "premika", "প্রেমিকা"),
    "boyfriend": ("bf", "boyfriend", "premik", "প্রেমিক"),
    "wife": ("wife", "bou", "স্ত্রী", "বউ"),
    "husband": ("husband", "jamai", "স্বামী", "জামাই"),
    "mother": ("mother", "ma", "mom", "মা"),
    "father": ("father", "baba", "dad", "বাবা"),
    "friend": ("friend", "bondhu", "বন্ধু"),
    "someone_special": ("someone special", "special person", "crush"),
    "sister": ("sister", "bon", "আপু", "বোন"),
    "brother": ("brother", "bhai", "ভাই"),
}

EMOTIONAL_KEYWORDS: tuple[str, ...] = (
    "mon kharap",
    "mon valo na",
    "bhalo lagche na",
    "valo lagche na",
    "sad",
    "depressed",
    "mood off",
    "mood kharap",
    "dukho lagche",
    "মন খারাপ",
    "মন ভালো নেই",
    "মুড অফ",
    "দুঃখ লাগছে",
    "ভালো লাগছে না",
    "ভাল লাগছে না",
)

UNSUPPORTED_KEYWORDS: tuple[str, ...] = (
    "relationship problem",
    "prem er problem",
)

VAGUE_SHOPPING_KEYWORDS: tuple[str, ...] = (
    "kichu dekhao",
    "kichu dekhan",
    "valo kichu",
    "bhalo kichu",
    "gift lagbe",
    "gift chai",
    "budget kom",
    "ki kinbo",
    "ki nibo",
    "kichu lagbe",
    "kichu chai",
    "kichu nibo",
    "daily use",
    "premium kichu",
    "cheap but good",
    "nijer jonno",
    "comforting kichu",
    "smart look",
    "new job",
    "impress korte",
    "what should i buy",
    "show something",
    "recommend something",
    "ভালো কিছু",
    "ভালো কিছু চাই",
    "কিছু দেখান",
    "কিছু চাই",
    "কিছু নেব",
    "বাজেট কম",
    "কি কিনব",
)

PERSONAL_BOT_KEYWORDS: tuple[str, ...] = (
    "tomar boyosh",
    "your age",
    "are you real",
    "tumi real",
    "tumi ke",
    "tomar nam",
    "are you human",
    "tumi manus",
    "who are you",
    "তোমার বয়স",
    "তোমার নাম",
    "তুমি কে",
    "তুমি মানুষ",
    "তুমি বট",
)

CONCRETE_PRODUCT_TERMS: tuple[str, ...] = (
    "saree",
    "sharee",
    "shari",
    "sari",
    "panjabi",
    "punjabi",
    "shirt",
    "pant",
    "shoes",
    "shoe",
    "bag",
    "watch",
    "perfume",
    "cosmetic",
    "makeup",
    "sunscreen",
    "face wash",
    "foundation",
    "charger",
    "laptop",
    "mobile",
    "lipstick",
    "jewelry",
    "jewellery",
    "necklace",
    "earring",
    "kameez",
    "kurti",
    "three piece",
    "3 piece",
    "dress",
    "শাড়ি",
    "পাঞ্জাবি",
    "শার্ট",
    "প্যান্ট",
    "জুতা",
    "জুতো",
    "ব্যাগ",
    "ঘড়ি",
    "পারফিউম",
    "লিপস্টিক",
    "গয়না",
)

SHOPPING_ACTION_TERMS: tuple[str, ...] = (
    "ache",
    "আছে",
    "available",
    "price",
    "dam",
    "দাম",
    "koto",
    "কত",
    "show",
    "dekhan",
    "দেখান",
    "find",
    "suggest",
    "recommend",
    "chai",
    "চাই",
    "kinbo",
    "কিনবো",
    "under",
    "budget",
)

SUPPORT_ACTION_TERMS: tuple[str, ...] = (
    "order",
    "delivery",
    "shipping",
    "refund",
    "return",
    "exchange",
    "payment",
    "cod",
    "track",
    "cancel",
    "অর্ডার",
    "ডেলিভারি",
    "ডেলিভারি চার্জ",
    "রিফান্ড",
    "রিটার্ন",
    "এক্সচেঞ্জ",
    "পেমেন্ট",
)

CATALOG_LIST_TERMS: tuple[str, ...] = (
    "product",
    "products",
    "item",
    "items",
    "catalog",
    "category",
    "categories",
    "পণ্য",
    "ক্যাটালগ",
)

BUSINESS_QUERY_TERMS: tuple[str, ...] = (
    "restock",
    "stock report",
    "inventory report",
    "sales report",
    "business signal",
    "which products should i restock",
)

_CASUAL_OFFTOPIC_TERMS: tuple[str, ...] = (
    "ki khobor",
    "kemon acho",
    "ki koro",
    "ki korcho",
    "ki khaiso",
    "khaiso",
    "kheyecho",
    "khaichen",
    "bored",
    "moja",
    "joke",
    "gan shonao",
    "golpo bolo",
    "funny",
    "time pass",
    "কি খবর",
    "কেমন আছ",
    "তুমি কি কর",
    "কি করছ",
    "কি খেয়েছ",
    "খেয়েছ",
    "বোর",
    "জোক",
    "গান শোনাও",
    "গল্প বল",
    "মজা",
)


def is_concrete_shopping_or_support(normalized_text: str) -> bool:
    """True when the message should bypass the boundary layer entirely.

    Returns True for:
      - real catalog queries (product + shopping action)
      - support actions (order/delivery/refund/exchange/payment)
      - catalog list requests
      - business-owner restock/inventory queries
    """
    concrete_product = has_any(normalized_text, CONCRETE_PRODUCT_TERMS)
    explicit_shopping_action = has_any(normalized_text, SHOPPING_ACTION_TERMS)
    support_action = has_any(normalized_text, SUPPORT_ACTION_TERMS)
    business_query = has_any(normalized_text, BUSINESS_QUERY_TERMS)
    catalog_list_request = explicit_shopping_action and has_any(normalized_text, CATALOG_LIST_TERMS)
    return (
        business_query
        or support_action
        or catalog_list_request
        or (concrete_product and explicit_shopping_action)
    )


def classify_fallback(normalized_text: str) -> dict[str, Any] | None:
    """Offline backstop. Returns a sub-intent dict or None if uncertain.

    Order matters: gift beats romantic (gift-for-gf is a sale, not a joke),
    occasion beats vague (a wedding shopper has a specific path), and the
    casual chitchat bucket only matches very short messages.
    """
    has_explicit_shopping = has_any(normalized_text, SHOPPING_ACTION_TERMS)
    concrete_product = has_any(normalized_text, CONCRETE_PRODUCT_TERMS)
    event = _detect_event(normalized_text)
    recipient = _detect_recipient(normalized_text)
    gift = has_any(normalized_text, GIFT_KEYWORDS)
    romantic = has_any(normalized_text, RELATIONSHIP_KEYWORDS) or matches_any(
        normalized_text, ROMANTIC_BOUNDARY_PATTERNS
    )
    impression = has_any(normalized_text, IMPRESSION_SHOPPING_KEYWORDS)

    if gift:
        return _intent(
            sub_intent="gift_recommendation",
            confidence=0.9,
            allowed_action="ask_clarifying_question",
            recommended_categories=gift_categories(recipient=recipient, event=event),
            slots={"recipient": recipient, "occasion": event},
            reasoning="Detected gift intent; redirecting into recipient, budget, and category.",
        )

    if romantic:
        return _intent(
            sub_intent="romantic_off_topic",
            confidence=0.9,
            allowed_action="playful_redirect",
            recommended_categories=("perfume", "outfit", "watch", "gift"),
            slots={"recipient": recipient},
            reasoning="Detected romantic/off-topic request; setting a friendly shopping boundary.",
        )

    if impression:
        return _intent(
            sub_intent="impression_shopping",
            confidence=0.84,
            allowed_action="ask_clarifying_question",
            recommended_categories=("perfume", "outfit", "watch", "gift"),
            slots={"recipient": recipient},
            reasoning="Detected hidden shopping intent around making a good impression.",
        )

    if has_any(normalized_text, PERSONAL_BOT_KEYWORDS):
        return _intent(
            sub_intent="personal_question_about_bot",
            confidence=0.76,
            allowed_action="short_humor_then_redirect",
            recommended_categories=("products", "gift", "outfit"),
            reasoning="Detected personal question about the bot; redirecting to store role.",
        )

    if event and not concrete_product:
        return _intent(
            sub_intent=f"occasion_{event}",
            confidence=0.88,
            allowed_action="occasion_recommendation",
            recommended_categories=EVENT_CATEGORY_MAP.get(event, ("outfit", "gift", "perfume")),
            slots={"occasion": event},
            reasoning="Detected occasion without a concrete product; converting it into a shopping path.",
        )

    if has_any(normalized_text, EMOTIONAL_KEYWORDS) and not concrete_product:
        return _intent(
            sub_intent="emotional_low_mood",
            confidence=0.83,
            allowed_action="empathetic_soft_product_suggestion",
            risk_level="medium",
            recommended_categories=("self-care", "perfume", "comfortable outfit", "gift"),
            slots={"mood": "low"},
            reasoning="Detected safe emotional message; responding empathetically with product-safe options.",
        )

    if has_any(normalized_text, UNSUPPORTED_KEYWORDS):
        return _intent(
            sub_intent="unsupported_redirect",
            confidence=0.82,
            allowed_action="safe_refusal_redirect",
            risk_level="medium",
            recommended_categories=("gift", "outfit", "perfume"),
            reasoning="Detected unsupported non-shopping advice request.",
        )

    if has_any(normalized_text, VAGUE_SHOPPING_KEYWORDS):
        return _intent(
            sub_intent="vague_shopping",
            confidence=0.78,
            allowed_action="ask_clarifying_question",
            recommended_categories=("gift", "outfit", "perfume", "bag", "watch"),
            reasoning="Detected vague shopping need; asking for budget and purpose.",
        )

    if _looks_casual(normalized_text) and not concrete_product and not has_explicit_shopping:
        return _intent(
            sub_intent="joke_chitchat",
            confidence=0.72,
            allowed_action="short_humor_then_redirect",
            recommended_categories=("products", "gift", "outfit"),
            reasoning="Detected casual off-topic message; keeping one friendly redirect.",
        )

    return None


def gift_categories(*, recipient: str | None, event: str | None) -> tuple[str, ...]:
    if event and event in EVENT_CATEGORY_MAP:
        return EVENT_CATEGORY_MAP[event]
    if recipient in {"girlfriend", "wife", "mother", "sister", "someone_special"}:
        return ("perfume", "bag", "cosmetics", "jewelry", "watch", "outfit")
    if recipient in {"boyfriend", "husband", "father", "brother"}:
        return ("perfume", "watch", "shirt", "panjabi", "wallet", "shoes")
    return ("perfume", "watch", "bag", "cosmetics", "outfit", "gift")


def _detect_event(text: str) -> str | None:
    for event, keywords in EVENT_KEYWORDS.items():
        if has_any(text, keywords):
            return event
    return None


def _detect_recipient(text: str) -> str | None:
    for recipient, keywords in RECIPIENT_KEYWORDS.items():
        if has_any(text, keywords):
            return recipient
    return None


def _looks_casual(text: str) -> bool:
    if len(text.split()) > 12:
        return False
    return has_any(text, _CASUAL_OFFTOPIC_TERMS)


def _intent(
    *,
    sub_intent: str,
    confidence: float,
    allowed_action: str,
    recommended_categories: tuple[str, ...],
    reasoning: str,
    risk_level: str = "low",
    slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "sub_intent": sub_intent,
        "confidence": confidence,
        "allowed_action": allowed_action,
        "risk_level": risk_level,
        "recommended_categories": recommended_categories,
        "slots": dict(slots or {}),
        "reasoning": reasoning,
    }


__all__ = [
    "EVENT_CATEGORY_MAP",
    "classify_fallback",
    "gift_categories",
    "is_concrete_shopping_or_support",
]
