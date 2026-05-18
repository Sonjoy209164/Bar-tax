from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

BANGLA_TEXT_PATTERN = re.compile(r"[\u0980-\u09ff]")
BANGLA_DIGIT_TRANS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


@dataclass(frozen=True)
class PoliteBoundaryDecision:
    boundary_type: str
    answer: str
    follow_up_question: str | None = None
    confidence: float = 0.85
    language: str = "english"
    slots: dict[str, Any] = field(default_factory=dict)
    recommended_categories: tuple[str, ...] = ()
    reasoning: tuple[str, ...] = ()


EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "wedding": (
        "biye",
        "biya",
        "biyete",
        "wedding",
        "marriage",
        "বিয়ে",
        "বিয়ে",
        "বিয়েতে",
        "বিয়েতে",
    ),
    "birthday": ("birthday", "jonmodin", "জন্মদিন", "বার্থডে"),
    "eid": ("eid", "ঈদ", "ইদ"),
    "puja": ("puja", "পূজা", "পুজা"),
    "office": ("office", "অফিস"),
    "interview": ("interview", "ইন্টারভিউ"),
    "date": ("date", "ডেট"),
    "party": ("party", "পার্টি"),
    "travel": ("travel", "tour", "trip", "ghurte", "ঘুরতে", "ভ্রমণ"),
}

EVENT_CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "wedding": ("saree", "panjabi", "shirt", "shoes", "perfume", "bag", "jewelry", "watch", "gift"),
    "birthday": ("gift", "outfit", "perfume", "watch", "bag", "cosmetics"),
    "eid": ("saree", "panjabi", "salwar_kameez", "shoes", "perfume", "bag"),
    "puja": ("saree", "panjabi", "jewelry", "bag", "shoes"),
    "office": ("shirt", "pant", "bag", "shoes", "watch", "perfume"),
    "interview": ("shirt", "pant", "shoes", "watch", "bag"),
    "date": ("outfit", "perfume", "watch", "gift"),
    "party": ("saree", "dress", "shirt", "shoes", "perfume", "bag", "jewelry"),
    "travel": ("bag", "shoes", "comfortable outfit", "watch", "perfume"),
}

GIFT_KEYWORDS = (
    "gift",
    "gifts",
    "present",
    "upohar",
    "উপহার",
    "গিফট",
    "gift dite",
    "gift nibo",
)

RELATIONSHIP_KEYWORDS = (
    "gf",
    "girlfriend",
    "g.f",
    "bf",
    "boyfriend",
    "b.f",
    "prem",
    "valobasha",
    "bhalobasha",
    "date korba",
    "biye korba",
    "প্রেম",
    "ভালোবাসা",
    "ভালবাসা",
)

ROMANTIC_BOUNDARY_PATTERNS = (
    r"\b(?:amar|amr|আমার)\s+(?:ekta|akta|একটা)?\s*(?:gf|girlfriend|bf|boyfriend)\s+(?:lagbe|chai|dorkar)\b",
    r"\b(?:tumi|apni|আপনি|তুমি)\s+.*(?:prem|date|biye)\s+(?:korba|korben|করবেন|করবা)\b",
    r"\b(?:prem|date)\s+(?:korba|korben|করবেন|করবা)\b",
)

RECIPIENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "girlfriend": ("gf", "girlfriend", "premika", "প্রেমিকা"),
    "boyfriend": ("bf", "boyfriend", "premik", "প্রেমিক"),
    "wife": ("wife", "bou", "স্ত্রী", "বউ"),
    "husband": ("husband", "jamai", "স্বামী", "জামাই"),
    "mother": ("mother", "ma", "mom", "মা"),
    "father": ("father", "baba", "dad", "বাবা"),
    "friend": ("friend", "bondhu", "বন্ধু"),
    "sister": ("sister", "bon", "আপু", "বোন"),
    "brother": ("brother", "bhai", "ভাই"),
}

EMOTIONAL_KEYWORDS = (
    "mon kharap",
    "mon valo na",
    "bhalo lagche na",
    "valo lagche na",
    "sad",
    "depressed",
    "মন খারাপ",
    "ভালো লাগছে না",
    "ভাল লাগছে না",
)

UNSUPPORTED_KEYWORDS = (
    "relationship problem",
    "prem er problem",
    "politics",
    "medical advice",
    "legal advice",
    "আইনি পরামর্শ",
    "ডাক্তারি পরামর্শ",
)

ABUSIVE_KEYWORDS = (
    "fuck",
    "shit",
    "bitch",
    "asshole",
)

CONCRETE_PRODUCT_TERMS = (
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
    "শাড়ি",
    "শাড়ি",
    "পাঞ্জাবি",
    "শার্ট",
    "প্যান্ট",
    "জুতা",
    "জুতো",
    "ব্যাগ",
    "ঘড়ি",
    "ঘড়ি",
    "পারফিউম",
    "লিপস্টিক",
    "গয়না",
    "গয়না",
)

SHOPPING_ACTION_TERMS = (
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
    "under",
    "budget",
)


def classify_polite_boundary(
    question: str,
    *,
    assistant_mode: str = "support",
    reply_style: str = "short",
) -> PoliteBoundaryDecision | None:
    text = _normalize(question)
    if not text:
        return None
    language = _detect_language(question)
    concrete_product = _has_any(text, CONCRETE_PRODUCT_TERMS)
    explicit_shopping_action = _has_any(text, SHOPPING_ACTION_TERMS)
    event = _detect_event(text)
    recipient = _detect_recipient(text)

    if _has_any(text, ABUSIVE_KEYWORDS):
        return _build_decision(
            boundary_type="unsafe_or_abusive",
            language=language,
            slots={},
            recommended_categories=(),
            confidence=0.88,
            reasoning=("Detected abusive or unsafe wording.",),
        )

    if _has_any(text, UNSUPPORTED_KEYWORDS):
        return _build_decision(
            boundary_type="unsupported_redirect",
            language=language,
            slots={},
            recommended_categories=("gift", "outfit", "perfume"),
            confidence=0.82,
            reasoning=("Detected unsupported non-shopping advice request.",),
        )

    gift = _has_any(text, GIFT_KEYWORDS)
    has_relationship_signal = _has_any(text, RELATIONSHIP_KEYWORDS) or _matches_any(text, ROMANTIC_BOUNDARY_PATTERNS)

    # A gift for girlfriend/boyfriend is a real commerce intent, not a joke.
    if gift:
        categories = _gift_categories(recipient=recipient, event=event)
        return _build_decision(
            boundary_type="gift_need",
            language=language,
            slots={"recipient": recipient, "occasion": event},
            recommended_categories=categories,
            confidence=0.9,
            reasoning=("Detected gift intent; redirecting into recipient, budget, and category selection.",),
        )

    if has_relationship_signal:
        return _build_decision(
            boundary_type="romantic_boundary",
            language=language,
            slots={"recipient": recipient},
            recommended_categories=("perfume", "outfit", "watch", "gift"),
            confidence=0.9,
            reasoning=("Detected romantic/off-topic request; setting a friendly shopping boundary.",),
        )

    if event and not concrete_product:
        categories = EVENT_CATEGORY_MAP.get(event, ("outfit", "gift", "perfume"))
        return _build_decision(
            boundary_type="event_need",
            language=language,
            slots={"occasion": event},
            recommended_categories=categories,
            confidence=0.88,
            reasoning=("Detected occasion without a concrete product; converting it into a shopping path.",),
        )

    if _has_any(text, EMOTIONAL_KEYWORDS) and not concrete_product and not explicit_shopping_action:
        return _build_decision(
            boundary_type="emotional_need",
            language=language,
            slots={"mood": "low"},
            recommended_categories=("self-care", "perfume", "comfortable outfit", "gift"),
            confidence=0.83,
            reasoning=("Detected safe emotional message; responding empathetically with product-safe options.",),
        )

    # Off-topic questions that are not greetings and not product searches.
    if _looks_like_casual_offtopic(text) and not concrete_product and not explicit_shopping_action:
        return _build_decision(
            boundary_type="off_topic_joke",
            language=language,
            slots={},
            recommended_categories=("products", "gift", "outfit"),
            confidence=0.72,
            reasoning=("Detected casual off-topic message; keeping one friendly redirect.",),
        )

    return None


def _build_decision(
    *,
    boundary_type: str,
    language: str,
    slots: dict[str, Any],
    recommended_categories: tuple[str, ...],
    confidence: float,
    reasoning: tuple[str, ...],
) -> PoliteBoundaryDecision:
    answer, follow_up = _template(
        boundary_type=boundary_type,
        language=language,
        slots=slots,
        categories=recommended_categories,
    )
    return PoliteBoundaryDecision(
        boundary_type=boundary_type,
        answer=answer,
        follow_up_question=follow_up,
        confidence=confidence,
        language=language,
        slots={k: v for k, v in slots.items() if v},
        recommended_categories=recommended_categories,
        reasoning=reasoning,
    )


def _template(
    *,
    boundary_type: str,
    language: str,
    slots: dict[str, Any],
    categories: tuple[str, ...],
) -> tuple[str, str | None]:
    occasion = slots.get("occasion")
    recipient = slots.get("recipient")
    cats = _category_phrase(categories, language=language)

    if language == "bangla":
        if boundary_type == "romantic_boundary":
            return (
                "আমি ডেটিং বা সম্পর্ক খুঁজে দিতে পারি না, কিন্তু কাউকে ইমপ্রেস করার জন্য পারফিউম, আউটফিট, ঘড়ি বা গিফট বেছে দিতে পারি।",
                "আপনি নিজের জন্য, নাকি কারও জন্য কিছু খুঁজছেন?",
            )
        if boundary_type == "event_need":
            return (
                f"ভালো, { _event_label(occasion, language) } এর জন্য {cats} সাজেস্ট করতে পারি।",
                "আপনি গেস্ট, কাছের বন্ধু, নাকি পরিবারের পক্ষ থেকে যাচ্ছেন?",
            )
        if boundary_type == "gift_need":
            return (
                f"গিফটের জন্য {cats} ভালো অপশন হতে পারে।",
                "কার জন্য গিফট এবং বাজেট কত?",
            )
        if boundary_type == "emotional_need":
            return (
                "শুনে খারাপ লাগল। নিজের জন্য আরামদায়ক কিছু, পারফিউম, সেলফ-কেয়ার আইটেম বা ছোট গিফট সাজেস্ট করতে পারি।",
                "আপনি কোন ধরনের জিনিস পছন্দ করেন?",
            )
        if boundary_type == "unsafe_or_abusive":
            return (
                "আমি ভদ্রভাবে শপিং, পণ্য, দাম, অর্ডার আর ডেলিভারি নিয়ে সাহায্য করতে পারি।",
                "কোন পণ্য খুঁজছেন?",
            )
        return (
            "এটা নিয়ে সরাসরি সাহায্য করতে পারব না, তবে আপনার পরিস্থিতির জন্য ঠিক পণ্য খুঁজে দিতে পারি।",
            "নিজের জন্য, গিফট, নাকি কোনো ইভেন্টের জন্য খুঁজছেন?",
        )

    if language == "banglish":
        if boundary_type == "romantic_boundary":
            return (
                "Girlfriend/boyfriend khuje dite parbo na, but impress korar jonno ekta smart perfume, outfit, watch, ba gift suggest korte pari.",
                "Apni nijer jonno, naki karo jonno kichu khujchen?",
            )
        if boundary_type == "event_need":
            return (
                f"Perfect, {_event_label(occasion, language)} er jonno {cats} suggest korte pari.",
                "Apni guest, close friend, naki family side?",
            )
        if boundary_type == "gift_need":
            who = f"{recipient} er jonno " if recipient else ""
            return (
                f"{who}gift er jonno {cats} bhalo option hote pare.",
                "Budget koto, and simple naki premium kichu chan?",
            )
        if boundary_type == "emotional_need":
            return (
                "Sorry je emon feel korchen. Nijer jonno comforting kichu, perfume, self-care item, ba simple outfit suggest korte pari.",
                "Apni kon type er product normally pochondo koren?",
            )
        if boundary_type == "unsafe_or_abusive":
            return (
                "Ami respectful bhabe shopping, product, price, order, delivery niye help korte pari.",
                "Kon product khujchen?",
            )
        return (
            "Eta niye directly help korte parbo na, but situation er jonno right product khujte help korte pari.",
            "Nijer jonno, gift, naki kono event er jonno khujchen?",
        )

    if boundary_type == "romantic_boundary":
        return (
            "I cannot help you find a girlfriend or boyfriend, but I can help you choose a perfume, outfit, watch, or gift that makes a good impression.",
            "Are you shopping for yourself or for someone special?",
        )
    if boundary_type == "event_need":
        return (
            f"Good occasion to shop smart. For {_event_label(occasion, language)}, I can suggest {cats}.",
            "Are you attending as a guest, close friend, or family member?",
        )
    if boundary_type == "gift_need":
        who = f"for your {recipient} " if recipient else ""
        return (
            f"For a gift {who}, I can suggest {cats}.",
            "What is your budget, and do you want something simple or premium?",
        )
    if boundary_type == "emotional_need":
        return (
            "Sorry you are feeling low. I can suggest something comforting: self-care, perfume, a simple outfit, or a small gift for yourself.",
            "What kind of product usually makes you feel good?",
        )
    if boundary_type == "unsafe_or_abusive":
        return (
            "I can help respectfully with shopping, products, prices, orders, and delivery.",
            "What product are you looking for?",
        )
    return (
        "I may not be able to help with that directly, but I can help you find the right product for the situation.",
        "Are you looking for something for yourself, a gift, or an event?",
    )


def _category_phrase(categories: tuple[str, ...], *, language: str) -> str:
    if not categories:
        return "products"
    if language == "bangla":
        translated = {
            "gift": "গিফট",
            "outfit": "আউটফিট",
            "perfume": "পারফিউম",
            "watch": "ঘড়ি",
            "bag": "ব্যাগ",
            "shoes": "জুতা",
            "jewelry": "গয়না",
            "saree": "শাড়ি",
            "panjabi": "পাঞ্জাবি",
        }
        labels = [translated.get(cat, cat) for cat in categories[:5]]
    else:
        labels = [cat.replace("_", " ") for cat in categories[:5]]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + ", or " + labels[-1]


def _event_label(event: str | None, language: str) -> str:
    if not event:
        return "this situation" if language == "english" else "ei situation"
    if language == "bangla":
        return {
            "wedding": "বিয়ে",
            "birthday": "জন্মদিন",
            "office": "অফিস",
            "interview": "ইন্টারভিউ",
            "eid": "ঈদ",
            "puja": "পূজা",
            "date": "ডেট",
            "party": "পার্টি",
            "travel": "ট্রাভেল",
        }.get(event, event)
    return event


def _gift_categories(*, recipient: str | None, event: str | None) -> tuple[str, ...]:
    if event and event in EVENT_CATEGORY_MAP:
        return EVENT_CATEGORY_MAP[event]
    if recipient in {"girlfriend", "wife", "mother", "sister"}:
        return ("perfume", "bag", "cosmetics", "jewelry", "watch", "outfit")
    if recipient in {"boyfriend", "husband", "father", "brother"}:
        return ("perfume", "watch", "shirt", "panjabi", "wallet", "shoes")
    return ("perfume", "watch", "bag", "cosmetics", "outfit", "gift")


def _detect_event(text: str) -> str | None:
    for event, keywords in EVENT_KEYWORDS.items():
        if _has_any(text, keywords):
            return event
    return None


def _detect_recipient(text: str) -> str | None:
    for recipient, keywords in RECIPIENT_KEYWORDS.items():
        if _has_any(text, keywords):
            return recipient
    return None


def _looks_like_casual_offtopic(text: str) -> bool:
    if len(text.split()) > 12:
        return False
    casual_terms = (
        "ki koro",
        "ki korcho",
        "bored",
        "moja",
        "joke",
        "funny",
        "time pass",
        "তুমি কি কর",
        "মজা",
    )
    return _has_any(text, casual_terms)


def _detect_language(text: str) -> str:
    if BANGLA_TEXT_PATTERN.search(text):
        return "bangla"
    normalized = _normalize(text)
    banglish_markers = (
        "amar",
        "amr",
        "ami",
        "tumi",
        "apni",
        "lagbe",
        "chai",
        "dorkar",
        "ache",
        "dekhan",
        "koto",
        "jonno",
        "er",
        "biye",
        "mon kharap",
    )
    return "banglish" if _has_any(normalized, banglish_markers) else "english"


def _normalize(text: str) -> str:
    normalized = text.casefold().translate(BANGLA_DIGIT_TRANS).replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9\u0980-\u09ff.\s+-]", " ", normalized)
    return " ".join(normalized.split())


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_has_phrase(text, phrase) for phrase in phrases)


def _has_phrase(text: str, phrase: str) -> bool:
    normalized = _normalize(phrase)
    if not normalized:
        return False
    pattern = re.escape(normalized).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text))


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)
