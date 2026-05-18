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
    risk_level: str = "low"
    allowed_action: str = "playful_redirect"
    handoff_recommended: bool = False
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
    "anniversary": ("anniversary", "barsiki", "বার্ষিকী", "অ্যানিভার্সারি"),
    "graduation": ("graduation", "convocation", "গ্র্যাজুয়েশন", "কনভোকেশন"),
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

GIFT_KEYWORDS = (
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

ROMANTIC_BOUNDARY_PATTERNS = (
    r"\b(?:amar|amr|আমার)\s+(?:ekta|akta|একটা)?\s*(?:gf|girlfriend|bf|boyfriend)\s+(?:lagbe|chai|dorkar)\b",
    r"\b(?:tumi|apni|আপনি|তুমি)\s+.*(?:prem|date|biye)\s+(?:korba|korben|করবেন|করবা)\b",
    r"\b(?:prem|date)\s+(?:korba|korben|করবেন|করবা)\b",
    r"\bwill\s+you\s+date\s+me\b",
)

IMPRESSION_SHOPPING_KEYWORDS = (
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

EMOTIONAL_KEYWORDS = (
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

SELF_HARM_KEYWORDS = (
    "kill myself",
    "suicide",
    "self harm",
    "nijeke mere felbo",
    "more jabo",
    "bachte chai na",
    "nijeke sesh kore debo",
    "মরে যাব",
    "বাঁচতে চাই না",
    "নিজেকে শেষ করে দেব",
    "নিজেকে মেরে ফেলব",
    "আত্মহত্যা",
)

POLITICAL_KEYWORDS = (
    "politics",
    "political",
    "election",
    "vote dibo",
    "vote debo",
    "kon party",
    "which party",
    "kake vote",
    "pm ke support",
    "support koro",
    "prime minister",
    "কাকে ভোট",
    "ভোট",
    "নির্বাচন",
    "কোন দল",
    "কোন পার্টি",
    "সরকার",
    "প্রধানমন্ত্রী",
    "রাজনীতি",
)

MEDICAL_ADVICE_KEYWORDS = (
    "medical advice",
    "doctor",
    "medicine khabo",
    "oshudh khabo",
    "treatment",
    "diagnose",
    "rash",
    "infection",
    "fever",
    "allergy",
    "pain",
    "ডাক্তারি পরামর্শ",
    "ডাক্তার",
    "মেডিসিন",
    "ঔষধ খাব",
    "ওষুধ খাব",
    "জ্বর",
    "ব্যথা",
    "এলার্জি",
    "র‍্যাশ",
    "ইনফেকশন",
    "চিকিৎসা",
)

LEGAL_ADVICE_KEYWORDS = (
    "legal advice",
    "case korle",
    "sue korbo",
    "contract legal",
    "contract",
    "lawyer",
    "আইনি পরামর্শ",
    "আইন",
    "আইনজীবী",
    "চুক্তি",
    "কেস",
    "মামলা",
    "উকিল",
)

UNSUPPORTED_KEYWORDS = (
    "relationship problem",
    "prem er problem",
)

SEVERE_ABUSIVE_KEYWORDS = (
    "i will kill",
    "kill you",
    "marbo",
    "mere felbo",
    "threat",
    "hate speech",
    "মারবো",
    "মেরে ফেলব",
)

MILD_ABUSIVE_KEYWORDS = (
    "fuck",
    "shit",
    "bitch",
    "asshole",
    "stupid",
    "faltu",
    "useless",
    "idiot",
    "nonsense",
    "boka",
    "bekar",
    "baje",
    "shala",
    "ফালতু",
    "বোকা",
    "বাজে",
    "গাধা",
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
    "chai",
    "চাই",
    "kinbo",
    "কিনবো",
    "under",
    "budget",
)

SUPPORT_ACTION_TERMS = (
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

CATALOG_LIST_TERMS = (
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

PAYMENT_SUPPORT_KEYWORDS = (
    "cod",
    "cash on delivery",
    "payment available",
    "payment method",
    "payment option",
    "bkash",
    "nagad",
    "rocket",
    "sslcommerz",
    "card payment",
    "ক্যাশ অন ডেলিভারি",
    "বিকাশ",
    "নগদ",
    "রকেট",
    "কার্ড পেমেন্ট",
    "পেমেন্ট",
)

ORDER_TRACKING_KEYWORDS = (
    "order track",
    "track order",
    "order status",
    "amar order track",
    "amar order kothay",
    "parcel kothay",
    "delivery status",
    "অর্ডার ট্র্যাক",
    "অর্ডার কোথায়",
    "পার্সেল কোথায়",
    "ডেলিভারি স্ট্যাটাস",
)

BUSINESS_QUERY_TERMS = (
    "restock",
    "stock report",
    "inventory report",
    "sales report",
    "business signal",
    "which products should i restock",
)

VAGUE_SHOPPING_KEYWORDS = (
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

PERSONAL_BOT_KEYWORDS = (
    "tomar boyosh",
    "your age",
    "are you real",
    "tumi real",
    "tumi ke",
    "tomar nam",
    "are you human",
    "tumi manus",
    "who are you",
    "তোমার বয়স",
    "তোমার নাম",
    "তুমি কে",
    "তুমি মানুষ",
    "তুমি বট",
)

RANDOM_TECH_KEYWORDS = (
    "python code",
    "javascript",
    "java code",
    "sql query",
    "ram kivabe kaj kore",
    "processor kivabe kaj kore",
    "write code",
    "website banai dao",
    "app banai dao",
    "api banai dao",
    "কোড লিখে",
    "কোড",
    "পাইথন",
    "জাভাস্ক্রিপ্ট",
    "এসকিউএল",
    "ওয়েবসাইট বানাও",
    "অ্যাপ বানাও",
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
    support_action = _has_any(text, SUPPORT_ACTION_TERMS)
    business_query = _has_any(text, BUSINESS_QUERY_TERMS)
    catalog_list_request = explicit_shopping_action and _has_any(text, CATALOG_LIST_TERMS)
    event = _detect_event(text)
    recipient = _detect_recipient(text)

    if _has_any(text, SELF_HARM_KEYWORDS):
        return _build_decision(
            boundary_type="self_harm_or_crisis",
            language=language,
            slots={},
            recommended_categories=(),
            confidence=0.96,
            risk_level="critical",
            allowed_action="crisis_safe_response",
            handoff_recommended=True,
            reasoning=("Detected crisis/self-harm language; commerce redirect is disabled.",),
        )

    if _has_any(text, SEVERE_ABUSIVE_KEYWORDS):
        return _build_decision(
            boundary_type="abusive_severe",
            language=language,
            slots={},
            recommended_categories=(),
            confidence=0.92,
            risk_level="high",
            allowed_action="stop_or_handoff",
            handoff_recommended=True,
            reasoning=("Detected severe abusive or threatening wording.",),
        )

    if _has_any(text, MILD_ABUSIVE_KEYWORDS):
        return _build_decision(
            boundary_type="abusive_mild",
            language=language,
            slots={},
            recommended_categories=(),
            confidence=0.86,
            risk_level="medium",
            allowed_action="deescalate",
            reasoning=("Detected mild abuse; de-escalating before continuing.",),
        )

    if _has_any(text, ORDER_TRACKING_KEYWORDS):
        return _build_decision(
            boundary_type="order_tracking_support",
            language=language,
            slots={"support_topic": "order_tracking"},
            recommended_categories=(),
            confidence=0.88,
            risk_level="low",
            allowed_action="store_support_redirect",
            reasoning=("Detected order tracking support request; asking for order ID or phone.",),
        )

    if _has_any(text, PAYMENT_SUPPORT_KEYWORDS):
        return _build_decision(
            boundary_type="payment_support",
            language=language,
            slots={"support_topic": "payment"},
            recommended_categories=(),
            confidence=0.86,
            risk_level="low",
            allowed_action="store_support_redirect",
            reasoning=("Detected payment support request; redirecting to payment policy/help.",),
        )

    # Concrete product, order, delivery, refund, and owner/business queries must
    # continue into the normal pipeline unless they are sensitive or unsafe.
    if business_query or support_action or catalog_list_request or (concrete_product and explicit_shopping_action):
        return None

    if _has_any(text, POLITICAL_KEYWORDS):
        return _build_decision(
            boundary_type="political",
            language=language,
            slots={},
            recommended_categories=(),
            confidence=0.88,
            risk_level="medium",
            allowed_action="safe_refusal_redirect",
            reasoning=("Detected political topic; keeping the brand neutral.",),
        )

    if _has_any(text, MEDICAL_ADVICE_KEYWORDS):
        return _build_decision(
            boundary_type="medical_or_health_advice",
            language=language,
            slots={},
            recommended_categories=("wellness", "self-care"),
            confidence=0.88,
            risk_level="high",
            allowed_action="safe_refusal_redirect",
            handoff_recommended=True,
            reasoning=("Detected medical advice request; avoiding diagnosis or treatment advice.",),
        )

    if _has_any(text, LEGAL_ADVICE_KEYWORDS):
        return _build_decision(
            boundary_type="legal_advice",
            language=language,
            slots={},
            recommended_categories=(),
            confidence=0.88,
            risk_level="high",
            allowed_action="safe_refusal_redirect",
            handoff_recommended=True,
            reasoning=("Detected legal advice request; avoiding legal guidance.",),
        )

    if _has_any(text, UNSUPPORTED_KEYWORDS):
        return _build_decision(
            boundary_type="unsupported_redirect",
            language=language,
            slots={},
            recommended_categories=("gift", "outfit", "perfume"),
            confidence=0.82,
            risk_level="medium",
            allowed_action="safe_refusal_redirect",
            reasoning=("Detected unsupported non-shopping advice request.",),
        )

    gift = _has_any(text, GIFT_KEYWORDS)
    has_relationship_signal = _has_any(text, RELATIONSHIP_KEYWORDS) or _matches_any(text, ROMANTIC_BOUNDARY_PATTERNS)
    has_impression_signal = _has_any(text, IMPRESSION_SHOPPING_KEYWORDS)

    # A gift for girlfriend/boyfriend is a real commerce intent, not a joke.
    if gift:
        categories = _gift_categories(recipient=recipient, event=event)
        return _build_decision(
            boundary_type="gift_recommendation",
            language=language,
            slots={"recipient": recipient, "occasion": event},
            recommended_categories=categories,
            confidence=0.9,
            risk_level="low",
            allowed_action="ask_clarifying_question",
            reasoning=("Detected gift intent; redirecting into recipient, budget, and category selection.",),
        )

    if has_relationship_signal:
        return _build_decision(
            boundary_type="romantic_off_topic",
            language=language,
            slots={"recipient": recipient},
            recommended_categories=("perfume", "outfit", "watch", "gift"),
            confidence=0.9,
            risk_level="low",
            allowed_action="playful_redirect",
            reasoning=("Detected romantic/off-topic request; setting a friendly shopping boundary.",),
        )

    if has_impression_signal:
        return _build_decision(
            boundary_type="impression_shopping",
            language=language,
            slots={"recipient": recipient},
            recommended_categories=("perfume", "outfit", "watch", "gift"),
            confidence=0.84,
            risk_level="low",
            allowed_action="ask_clarifying_question",
            reasoning=("Detected a hidden shopping need around making a good impression.",),
        )

    if _has_any(text, PERSONAL_BOT_KEYWORDS):
        return _build_decision(
            boundary_type="personal_question_about_bot",
            language=language,
            slots={},
            recommended_categories=("products", "gift", "outfit"),
            confidence=0.76,
            risk_level="low",
            allowed_action="short_humor_then_redirect",
            reasoning=("Detected personal question about the bot; redirecting to store role.",),
        )

    if event and not concrete_product:
        categories = EVENT_CATEGORY_MAP.get(event, ("outfit", "gift", "perfume"))
        return _build_decision(
            boundary_type=f"occasion_{event}",
            language=language,
            slots={"occasion": event},
            recommended_categories=categories,
            confidence=0.88,
            risk_level="low",
            allowed_action="occasion_recommendation",
            reasoning=("Detected occasion without a concrete product; converting it into a shopping path.",),
        )

    if _has_any(text, EMOTIONAL_KEYWORDS) and not concrete_product:
        return _build_decision(
            boundary_type="emotional_low_mood",
            language=language,
            slots={"mood": "low"},
            recommended_categories=("self-care", "perfume", "comfortable outfit", "gift"),
            confidence=0.83,
            risk_level="medium",
            allowed_action="empathetic_soft_product_suggestion",
            reasoning=("Detected safe emotional message; responding empathetically with product-safe options.",),
        )

    if _has_any(text, VAGUE_SHOPPING_KEYWORDS):
        return _build_decision(
            boundary_type="vague_shopping",
            language=language,
            slots={},
            recommended_categories=("gift", "outfit", "perfume", "bag", "watch"),
            confidence=0.78,
            risk_level="low",
            allowed_action="ask_clarifying_question",
            reasoning=("Detected vague shopping need; asking for budget and purpose.",),
        )

    if _has_any(text, RANDOM_TECH_KEYWORDS):
        return _build_decision(
            boundary_type="random_tech",
            language=language,
            slots={},
            recommended_categories=(),
            confidence=0.78,
            risk_level="low",
            allowed_action="safe_refusal_redirect",
            reasoning=("Detected non-catalog technical request; redirecting to store support.",),
        )

    # Off-topic questions that are not greetings and not product searches.
    if _looks_like_casual_offtopic(text) and not concrete_product and not explicit_shopping_action:
        return _build_decision(
            boundary_type="joke_chitchat",
            language=language,
            slots={},
            recommended_categories=("products", "gift", "outfit"),
            confidence=0.72,
            risk_level="low",
            allowed_action="short_humor_then_redirect",
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
    risk_level: str,
    allowed_action: str,
    reasoning: tuple[str, ...],
    handoff_recommended: bool = False,
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
        risk_level=risk_level,
        allowed_action=allowed_action,
        handoff_recommended=handoff_recommended,
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
        if boundary_type == "self_harm_or_crisis":
            return (
                "আপনি যদি এখন নিরাপদ না অনুভব করেন, দয়া করে কাছের বিশ্বস্ত কাউকে বা স্থানীয় জরুরি সহায়তায় যোগাযোগ করুন। আমি শপিংয়ে সাহায্য করতে পারি, কিন্তু এই মুহূর্তে আপনার নিরাপত্তাই সবচেয়ে গুরুত্বপূর্ণ।",
                None,
            )
        if boundary_type == "romantic_off_topic":
            return (
                "আমি ডেটিং বা সম্পর্ক খুঁজে দিতে পারি না, কিন্তু কাউকে ইমপ্রেস করার জন্য পারফিউম, আউটফিট, ঘড়ি বা গিফট বেছে দিতে পারি।",
                "আপনি নিজের জন্য, নাকি কারও জন্য কিছু খুঁজছেন?",
            )
        if boundary_type == "impression_shopping":
            return (
                "কাউকে ইমপ্রেস করার জন্য পারফিউম, আউটফিট, ঘড়ি বা গিফট ভালো অপশন হতে পারে।",
                "বাজেট কত এবং সিম্পল নাকি প্রিমিয়াম কিছু চান?",
            )
        if boundary_type.startswith("occasion_"):
            return (
                f"ভালো, { _event_label(occasion, language) } এর জন্য {cats} সাজেস্ট করতে পারি।",
                "আপনি গেস্ট, কাছের বন্ধু, নাকি পরিবারের পক্ষ থেকে যাচ্ছেন?",
            )
        if boundary_type == "gift_recommendation":
            return (
                f"গিফটের জন্য {cats} ভালো অপশন হতে পারে।",
                "কার জন্য গিফট এবং বাজেট কত?",
            )
        if boundary_type == "emotional_low_mood":
            return (
                "শুনে খারাপ লাগল। নিজের জন্য আরামদায়ক কিছু, পারফিউম, সেলফ-কেয়ার আইটেম বা ছোট গিফট সাজেস্ট করতে পারি।",
                "আপনি কোন ধরনের জিনিস পছন্দ করেন?",
            )
        if boundary_type in {"abusive_mild", "abusive_severe"}:
            return (
                "আমি ভদ্রভাবে শপিং, পণ্য, দাম, অর্ডার আর ডেলিভারি নিয়ে সাহায্য করতে পারি।",
                "কোন পণ্য খুঁজছেন?",
            )
        if boundary_type == "order_tracking_support":
            return (
                "অর্ডার ট্র্যাক করতে অর্ডার আইডি বা ফোন নম্বর দরকার।",
                "অর্ডার আইডি বা ফোন নম্বর দিন।",
            )
        if boundary_type == "payment_support":
            return (
                "পেমেন্ট বা COD সম্পর্কে সাহায্য করতে পারি। নির্দিষ্ট অর্ডার হলে চেকআউট/স্টোর পলিসি অনুযায়ী কনফার্ম করতে হবে।",
                "আপনি COD, bKash/Nagad, নাকি কার্ড পেমেন্ট জানতে চান?",
            )
        if boundary_type == "personal_question_about_bot":
            return (
                "আমি এই স্টোরের শপিং অ্যাসিস্ট্যান্ট। পণ্য, দাম, অর্ডার, ডেলিভারি আর গিফট সাজেশনে সাহায্য করতে পারি।",
                "কোন ধরনের পণ্য খুঁজছেন?",
            )
        if boundary_type == "joke_chitchat":
            return (
                "হাহা, আমি আড্ডা দিতে পারি, কিন্তু মূল কাজ শপিংয়ে সাহায্য করা। পণ্য, গিফট, আউটফিট বা ডিল সাজেস্ট করতে পারি।",
                "কোন ধরনের কিছু খুঁজছেন?",
            )
        if boundary_type == "political":
            return (
                "রাজনৈতিক বিষয়ে আমি নিরপেক্ষ থাকি। পণ্য, দাম, অর্ডার, ডেলিভারি বা গিফট সাজেশনে সাহায্য করতে পারি।",
                "কোন ধরনের পণ্য খুঁজছেন?",
            )
        if boundary_type == "medical_or_health_advice":
            return (
                "আমি মেডিকেল পরামর্শ দিতে পারি না। ডাক্তার বা ফার্মাসিস্টের সাথে কথা বলা ভালো। পণ্যের লেবেল, ইনগ্রেডিয়েন্ট বা ওয়েলনেস আইটেম দেখতে চাইলে সাহায্য করতে পারি।",
                None,
            )
        if boundary_type == "legal_advice":
            return (
                "আমি আইনি পরামর্শ দিতে পারি না। আইনজীবীর সাথে কথা বলা ভালো। স্টোর পলিসি, অর্ডার, রিফান্ড বা ডেলিভারি নিয়ে সাহায্য করতে পারি।",
                None,
            )
        if boundary_type == "vague_shopping":
            return (
                "অবশ্যই। বাজেট আর উদ্দেশ্য বললে ভালো অপশন সাজেস্ট করতে পারব।",
                "নিজের জন্য, গিফট, অফিস, ইভেন্ট, নাকি ডেইলি ইউজ?",
            )
        return (
            "এটা নিয়ে সরাসরি সাহায্য করতে পারব না, তবে আপনার পরিস্থিতির জন্য ঠিক পণ্য খুঁজে দিতে পারি।",
            "নিজের জন্য, গিফট, নাকি কোনো ইভেন্টের জন্য খুঁজছেন?",
        )

    if language == "banglish":
        if boundary_type == "self_harm_or_crisis":
            return (
                "Apni jodi ekhon safe feel na koren, please ekjon trusted manush ba local emergency support er sathe jogajog korun. Ami shopping help korte pari, but ei moment e apnar safety first.",
                None,
            )
        if boundary_type == "romantic_off_topic":
            return (
                "Girlfriend/boyfriend khuje dite parbo na, but impress korar jonno ekta smart perfume, outfit, watch, ba gift suggest korte pari.",
                "Apni nijer jonno, naki karo jonno kichu khujchen?",
            )
        if boundary_type == "impression_shopping":
            return (
                "Kauke impress korte chaile perfume, smart outfit, watch, ba gift er moddhe bhalo option suggest korte pari.",
                "Budget koto, and simple naki premium kichu chan?",
            )
        if boundary_type.startswith("occasion_"):
            return (
                f"Perfect, {_event_label(occasion, language)} er jonno {cats} suggest korte pari.",
                "Apni guest, close friend, naki family side?",
            )
        if boundary_type == "gift_recommendation":
            who = f"{recipient} er jonno " if recipient else ""
            return (
                f"{who}gift er jonno {cats} bhalo option hote pare.",
                "Budget koto, and simple naki premium kichu chan?",
            )
        if boundary_type == "emotional_low_mood":
            return (
                "Sorry je emon feel korchen. Nijer jonno comforting kichu, perfume, self-care item, ba simple outfit suggest korte pari.",
                "Apni kon type er product normally pochondo koren?",
            )
        if boundary_type in {"abusive_mild", "abusive_severe"}:
            return (
                "Ami respectful bhabe shopping, product, price, order, delivery niye help korte pari.",
                "Kon product khujchen?",
            )
        if boundary_type == "order_tracking_support":
            return (
                "Order track korte order ID ba phone number lagbe.",
                "Order ID ba phone number din.",
            )
        if boundary_type == "payment_support":
            return (
                "Payment or COD niye help korte pari. Specific order hole checkout/store policy onujayi confirm korte hobe.",
                "Apni COD, bKash/Nagad, naki card payment jante chan?",
            )
        if boundary_type == "personal_question_about_bot":
            return (
                "Ami ei store er shopping assistant. Product, price, order, delivery, and gift suggestion niye help korte pari.",
                "Kon product ba category khujchen?",
            )
        if boundary_type == "joke_chitchat":
            return (
                "Haha, adda dite pari, but amar main kaj shopping e help kora. Product, gift, outfit, ba deal suggest korte pari.",
                "Kon type er kichu khujchen?",
            )
        if boundary_type == "political":
            return (
                "Political topic e ami neutral thaki. Ami product, price, order, delivery, gift, or shopping suggestions niye help korte pari.",
                "Kon type er product khujchen?",
            )
        if boundary_type == "medical_or_health_advice":
            return (
                "Medical advice dite parbo na. Doctor or pharmacist er sathe check kora best. Product label, ingredient, or available wellness item dekhte chaile ami help korte pari.",
                None,
            )
        if boundary_type == "legal_advice":
            return (
                "Legal advice dite parbo na. Qualified lawyer er sathe check kora best. Store policy, order, refund, or delivery niye question thakle ami help korte pari.",
                None,
            )
        if boundary_type == "vague_shopping":
            return (
                "Sure. Budget and purpose bolle ami best options suggest korte parbo.",
                "Nijer jonno, gift, office, event, naki daily use?",
            )
        if boundary_type == "random_tech":
            return (
                "Eta amar shop support er baire. Ami product, price, order, delivery, gift, and shopping suggestions niye help korte pari.",
                "Kon product ba category khujchen?",
            )
        return (
            "Eta niye directly help korte parbo na, but situation er jonno right product khujte help korte pari.",
            "Nijer jonno, gift, naki kono event er jonno khujchen?",
        )

    if boundary_type == "self_harm_or_crisis":
        return (
            "If you may be in immediate danger, please contact local emergency support or someone you trust right now. I can help with shopping, but your safety comes first.",
            None,
        )
    if boundary_type == "romantic_off_topic":
        return (
            "I cannot help you find a girlfriend or boyfriend, but I can help you choose a perfume, outfit, watch, or gift that makes a good impression.",
            "Are you shopping for yourself or for someone special?",
        )
    if boundary_type == "impression_shopping":
        return (
            "If you want to make a good impression, I can suggest a perfume, outfit, watch, or gift from the store.",
            "What is your budget, and do you want something simple or premium?",
        )
    if boundary_type.startswith("occasion_"):
        return (
            f"Good occasion to shop smart. For {_event_label(occasion, language)}, I can suggest {cats}.",
            "Are you attending as a guest, close friend, or family member?",
        )
    if boundary_type == "gift_recommendation":
        who = f"for your {recipient} " if recipient else ""
        return (
            f"For a gift {who}, I can suggest {cats}.",
            "What is your budget, and do you want something simple or premium?",
        )
    if boundary_type == "emotional_low_mood":
        return (
            "Sorry you are feeling low. I can suggest something comforting: self-care, perfume, a simple outfit, or a small gift for yourself.",
            "What kind of product usually makes you feel good?",
        )
    if boundary_type in {"abusive_mild", "abusive_severe"}:
        return (
            "I can help respectfully with shopping, products, prices, orders, and delivery.",
            "What product are you looking for?",
        )
    if boundary_type == "order_tracking_support":
        return (
            "I can help track an order, but I need the order ID or phone number first.",
            "Please share the order ID or phone number.",
        )
    if boundary_type == "payment_support":
        return (
            "I can help with payment or COD questions. For a specific order, availability depends on checkout and store policy.",
            "Do you want COD, bKash/Nagad, or card payment information?",
        )
    if boundary_type == "personal_question_about_bot":
        return (
            "I am this store's shopping assistant. I can help with products, prices, orders, delivery, and gift suggestions.",
            "What product or category are you looking for?",
        )
    if boundary_type == "joke_chitchat":
        return (
            "Haha, I can chat a little, but I should keep it shopping-focused. I can help with products, gifts, outfits, or deals.",
            "What kind of item are you looking for?",
        )
    if boundary_type == "political":
        return (
            "I stay neutral on political topics. I can help with products, prices, delivery, orders, or gift suggestions.",
            "What are you shopping for?",
        )
    if boundary_type == "medical_or_health_advice":
        return (
            "I cannot provide medical advice. Please consult a qualified doctor or pharmacist. I can help with product label information, ingredients, or available wellness items.",
            None,
        )
    if boundary_type == "legal_advice":
        return (
            "I cannot provide legal advice. Please consult a qualified lawyer. I can help with store policies, orders, refunds, or delivery questions.",
            None,
        )
    if boundary_type == "vague_shopping":
        return (
            "Sure. Tell me your budget and purpose, and I can suggest the best options.",
            "Is it for yourself, a gift, office, an event, or daily use?",
        )
    if boundary_type == "random_tech":
        return (
            "That is outside my store-support role. I can help with products, prices, orders, delivery, gifts, and shopping suggestions.",
            "What product or category are you looking for?",
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
            "anniversary": "বার্ষিকী",
            "graduation": "গ্র্যাজুয়েশন",
            "pohela_boishakh": "পহেলা বৈশাখ",
            "office": "অফিস",
            "new_job": "নতুন চাকরি",
            "interview": "ইন্টারভিউ",
            "eid": "ঈদ",
            "puja": "পূজা",
            "date": "ডেট",
            "party": "পার্টি",
            "travel": "ট্রাভেল",
        }.get(event, event)
    return {
        "new_job": "new job",
        "pohela_boishakh": "Pohela Boishakh",
    }.get(event, event)


def _gift_categories(*, recipient: str | None, event: str | None) -> tuple[str, ...]:
    if event and event in EVENT_CATEGORY_MAP:
        return EVENT_CATEGORY_MAP[event]
    if recipient in {"girlfriend", "wife", "mother", "sister", "someone_special"}:
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
        "কি খেয়েছ",
        "খেয়েছ",
        "বোর",
        "জোক",
        "গান শোনাও",
        "গল্প বল",
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
