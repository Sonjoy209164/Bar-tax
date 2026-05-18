from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any

from app.core.schemas import InventoryItemRecord, InventorySearchFilters
from app.inventory.banglish_normalizer import augment_with_bangla
from app.inventory.fuzzy_corrector import augment_with_corrections
from app.inventory.llm_intent_classifier import (
    ClassifiedIntent,
    classify_intent_llm,
)
from app.inventory.llm_slot_extractor import (
    extract_slots_via_llm,
    is_ollama_available,
    merge_llm_slots_into_fashion_slots,
)


BANGLA_DIGIT_TRANS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
BANGLA_TEXT_PATTERN = re.compile(r"[\u0980-\u09ff]")


def normalize_fashion_text(text: object | None) -> str:
    if text is None:
        return ""
    normalized = str(text).casefold().translate(BANGLA_DIGIT_TRANS).replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9\u0980-\u09ff.\s+-]", " ", normalized)
    return " ".join(normalized.split())


@dataclass(frozen=True)
class FashionRetailSlots:
    category_key: str | None = None
    category_label: str | None = None
    color: str | None = None
    color_family: str | None = None
    size: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    fabric: str | None = None
    work_type: str | None = None
    occasion: str | None = None
    style: str | None = None
    gender: str | None = None
    design_id: str | None = None
    wants_in_stock: bool = False
    intent: str = "fashion_search"
    language: str = "english"
    evidence: tuple[str, ...] = ()
    confidence: float = 1.0
    ambiguity_reason: str | None = None

    def to_plan_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "retail_domain": "fashion",
            "intent": self.intent,
        }
        for key in (
            "category_key",
            "category_label",
            "color",
            "color_family",
            "size",
            "budget_min",
            "budget_max",
            "fabric",
            "work_type",
            "occasion",
            "style",
            "gender",
            "design_id",
            "wants_in_stock",
            "language",
        ):
            value = getattr(self, key)
            if value is None:
                continue
            if isinstance(value, bool) and not value:
                continue
            payload[key] = value
        if self.evidence:
            payload["evidence"] = list(self.evidence)
        return payload


@dataclass(frozen=True)
class FashionRetailOutcome:
    answer: str
    intent: str
    product_ids: tuple[str, ...] = ()
    cross_sell_product_ids: tuple[str, ...] = ()
    total_matches: int = 0
    confidence: float = 0.0
    slots: FashionRetailSlots = field(default_factory=FashionRetailSlots)
    follow_up_question: str | None = None
    abstained: bool = False
    abstention_reason: str | None = None
    reasoning_steps: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ScoredItem:
    item: InventoryItemRecord
    score: float
    reasons: tuple[str, ...] = ()


class FashionRetailAssistant:
    """Deterministic customer-support layer for variant-heavy fashion retail catalogs."""

    CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
        "saree": ("saree", "sarees", "sari", "saris", "sharee", "shari", "শাড়ি", "শাড়ি", "সারি"),
        "blouse": ("blouse", "blouses", "ready blouse", "stitched blouse", "ব্লাউজ", "রেডি ব্লাউজ"),
        "panjabi": ("panjabi", "punjabi", "kurta", "kurta pajama", "পাঞ্জাবি", "পাঞ্জাবী", "কুর্তা"),
        "kurti": ("kurti", "kameez", "tops", "কুর্তি", "কামিজ", "টপ"),
        "salwar_kameez": (
            "salwar kameez",
            "three piece",
            "3 piece",
            "three-piece",
            "dress",
            "salwar",
            "সালোয়ার কামিজ",
            "সালওয়ার কামিজ",
            "থ্রি পিস",
            "৩ পিস",
            "ড্রেস",
        ),
        "dupatta": ("dupatta", "orna", "orhna", "scarf", "দুপাট্টা", "ওড়না", "ওড়না", "স্কার্ফ"),
        "shawl": ("shawl", "stole", "শাল", "স্টোল"),
        "bag": ("bag", "bags", "handbag", "tote", "clutch", "purse", "wallet", "ব্যাগ", "হ্যান্ডব্যাগ", "ক্লাচ", "পার্স", "ওয়ালেট", "ওয়ালেট"),
        "shoes": ("shoe", "shoes", "sandal", "sandals", "heel", "heels", "flat", "loafer", "loafers", "sneaker", "sneakers", "জুতা", "জুতো", "স্যান্ডেল", "হিল"),
        "shirt": ("shirt", "shirts", "formal shirt", "casual shirt", "শার্ট"),
        "pant": ("pant", "pants", "trouser", "trousers", "chino", "chinos", "প্যান্ট", "ট্রাউজার"),
        "watch": ("watch", "watches", "ঘড়ি", "ঘড়ি", "ওয়াচ", "ওয়াচ"),
        "perfume": ("perfume", "perfumes", "attar", "body spray", "fragrance", "পারফিউম", "আতর", "বডি স্প্রে", "সুগন্ধি"),
        "cosmetics": (
            "cosmetic",
            "cosmetics",
            "makeup",
            "lipstick",
            "kajal",
            "eyeliner",
            "foundation",
            "compact",
            "মেকআপ",
            "লিপস্টিক",
            "কাজল",
            "ফাউন্ডেশন",
            "কমপ্যাক্ট",
        ),
        "beauty": (
            "beauty",
            "beauty product",
            "beauty products",
            "skincare",
            "skin care",
            "sunscreen",
            "sun screen",
            "face wash",
            "facewash",
            "cream",
            "serum",
            "বিউটি",
            "স্কিনকেয়ার",
            "স্কিন কেয়ার",
            "সানস্ক্রিন",
            "ফেস ওয়াশ",
            "ফেসওয়াশ",
        ),
        "jewelry": (
            "jewelry",
            "jewellery",
            "ornament",
            "ornaments",
            "necklace",
            "bangle",
            "bangles",
            "churi",
            "earring",
            "earrings",
            "jhumka",
            "goyna",
            "goyena",
            "churi",
            "গয়না",
            "গয়না",
            "জুয়েলারি",
            "জুয়েলারি",
            "চুড়ি",
            "চুড়ি",
            "বালা",
            "নেকলেস",
            "হার",
            "কানের দুল",
            "ঝুমকা",
        ),
        "accessories": ("accessory", "accessories", "matching item", "matching items", "এক্সেসরিজ", "অ্যাক্সেসরিজ", "ম্যাচিং আইটেম"),
    }
    CATEGORY_LABELS: dict[str, str] = {
        "saree": "Saree",
        "blouse": "Blouse",
        "panjabi": "Panjabi",
        "kurti": "Kurti",
        "salwar_kameez": "Salwar Kameez",
        "dupatta": "Dupatta",
        "shawl": "Shawl",
        "bag": "Bags",
        "shoes": "Shoes",
        "shirt": "Shirt",
        "pant": "Pant",
        "watch": "Watch",
        "perfume": "Perfume",
        "cosmetics": "Cosmetics",
        "beauty": "Beauty",
        "jewelry": "Jewelry",
        "accessories": "Accessories",
    }
    ITEM_FASHION_CATEGORY_TERMS = {
        "saree",
        "sari",
        "blouse",
        "panjabi",
        "punjabi",
        "kurta",
        "kurti",
        "salwar",
        "kameez",
        "dupatta",
        "shawl",
        "jewelry",
        "jewellery",
        "bangles",
        "necklace",
        "earrings",
        "clutch",
        "handbag",
        "bag",
        "shoes",
        "shoe",
        "sandal",
        "heel",
        "loafer",
        "sneaker",
        "shirt",
        "pant",
        "trouser",
        "watch",
        "perfume",
        "fragrance",
        "attar",
        "cosmetic",
        "cosmetics",
        "makeup",
        "lipstick",
        "kajal",
        "sunscreen",
        "skincare",
        "face wash",
        "foundation",
        "ব্যাগ",
        "শাড়ি",
        "শাড়ি",
        "ব্লাউজ",
        "পাঞ্জাবি",
        "জুতা",
        "জুতো",
        "শার্ট",
        "প্যান্ট",
        "ঘড়ি",
        "ঘড়ি",
        "পারফিউম",
        "লিপস্টিক",
        "কাজল",
        "সানস্ক্রিন",
        "গয়না",
        "গয়না",
        "চুড়ি",
        "চুড়ি",
    }
    TECH_CONTEXT_TERMS = {
        "laptop",
        "phone",
        "tablet",
        "charger",
        "power bank",
        "ssd",
        "keyboard",
        "mouse",
        "monitor",
        "webcam",
        "headphone",
        "headphones",
        "earbuds",
        "router",
        "usb",
        "camera",
    }
    COLOR_ALIASES: dict[str, tuple[str, str, tuple[str, ...]]] = {
        "royal blue": ("royal blue", "blue", ("royal blue", "royal nil", "রয়েল ব্লু", "রয়েল ব্লু", "রয়েল নীল", "রয়েল নীল")),
        "navy blue": ("navy blue", "blue", ("navy", "navy blue", "নেভি", "নেভি ব্লু", "নেভি নীল")),
        "bottle green": ("bottle green", "green", ("bottle green", "বোতল সবুজ", "বটল গ্রিন")),
        "mint green": ("mint green", "green", ("mint", "mint green", "মিন্ট", "মিন্ট গ্রিন", "মিন্ট সবুজ")),
        "antique gold": ("antique gold", "gold", ("antique gold", "এন্টিক গোল্ড", "অ্যান্টিক গোল্ড", "এন্টিক সোনালি")),
        "red": ("red", "red", ("red", "lal", "লাল")),
        "maroon": ("maroon", "red", ("maroon", "মেরুন")),
        "blue": ("blue", "blue", ("blue", "nil", "neel", "নীল", "ব্লু")),
        "green": ("green", "green", ("green", "sobuj", "সবুজ", "গ্রিন")),
        "gold": ("gold", "gold", ("gold", "golden", "sonali", "সোনালি", "গোল্ড", "সোনালী")),
        "rose gold": ("rose gold", "gold", ("rose gold", "রোজ গোল্ড")),
        "black": ("black", "black", ("black", "kalo", "কালো", "ব্ল্যাক")),
        "white": ("white", "white", ("white", "shada", "সাদা", "শাদা", "হোয়াইট", "হোয়াইট")),
        "nude": ("nude", "beige", ("nude", "nyud", "নুড")),
        "mustard": ("mustard", "yellow", ("mustard",)),
        "yellow": ("yellow", "yellow", ("yellow", "holud", "হলুদ", "ইয়েলো", "ইয়েলো")),
        "peach": ("peach", "peach", ("peach",)),
        "lavender": ("lavender", "purple", ("lavender",)),
        "purple": ("purple", "purple", ("purple", "পার্পল", "বেগুনি")),
        "pink": ("pink", "pink", ("pink", "golapi", "গোলাপি", "পিংক")),
        "silver": ("silver", "silver", ("silver", "রুপালি", "রূপালি", "সিলভার")),
        "cream": ("cream", "cream", ("cream", "ক্রিম")),
        "beige": ("beige", "beige", ("beige",)),
        "brown": ("brown", "brown", ("brown", "বাদামি", "ব্রাউন")),
        "gray": ("gray", "gray", ("gray", "grey", "ধূসর", "গ্রে")),
        "orange": ("orange", "orange", ("orange", "কমলা", "অরেঞ্জ")),
        "indigo": ("indigo", "blue", ("indigo",)),
    }
    FABRIC_ALIASES: dict[str, tuple[str, ...]] = {
        "jamdani": ("jamdani", "dhakai jamdani", "জামদানি", "ঢাকাই জামদানি"),
        "katan": ("katan", "silk katan", "কাতান", "সিল্ক কাতান"),
        "silk": ("silk", "half silk", "half-silk", "soft silk", "সিল্ক", "হাফ সিল্ক"),
        "muslin": ("muslin", "soft muslin", "মসলিন", "মসলিনের"),
        "cotton": ("cotton", "suti", "সুতি", "কটন"),
        "cotton blend": ("cotton blend", "কটন ব্লেন্ড"),
        "linen": ("linen", "লিনেন"),
        "georgette": ("georgette",),
        "leather": ("leather", "লেদার"),
        "synthetic leather": ("synthetic leather", "faux leather", "rexine"),
        "chiffon": ("chiffon",),
        "organza": ("organza",),
        "khadi": ("khadi",),
        "handloom": ("handloom",),
    }
    WORK_ALIASES: dict[str, tuple[str, ...]] = {
        "zari": ("zari", "জরি", "জারী"),
        "meena": ("meena", "meena work", "মিনা", "মীনা", "মীনা কাজ"),
        "embroidery": ("embroidery", "embroidered", "এম্ব্রয়ডারি", "এম্ব্রয়ডারি", "সূচিকর্ম"),
        "block print": ("block print", "block-print", "ব্লক প্রিন্ট"),
        "buti": ("buti", "বুটি"),
        "floral": ("floral", "flower", "ফ্লোরাল", "ফুল"),
        "plain": ("plain", "সিম্পল", "প্লেইন"),
        "mirror work": ("mirror work",),
    }
    OCCASION_ALIASES: dict[str, tuple[str, ...]] = {
        "bridal": ("bridal", "bride", "কনে", "ব্রাইডাল"),
        "wedding": ("wedding", "biye", "biya", "marriage", "বিয়ে", "বিয়ে", "বিয়ের", "বিয়ের"),
        "reception": ("reception",),
        "party": ("party", "program", "পার্টি", "প্রোগ্রাম"),
        "office": ("office", "work", "office e", "অফিস", "কাজে"),
        "casual": ("casual", "ক্যাজুয়াল", "ক্যাজুয়াল"),
        "daily wear": ("daily wear", "everyday", "regular", "প্রতিদিন", "রেগুলার", "দৈনন্দিন"),
        "eid": ("eid", "ঈদ"),
        "puja": ("puja", "পূজা"),
        "pohela boishakh": ("pohela boishakh", "boishakh", "পহেলা বৈশাখ", "বৈশাখ"),
        "gift": ("gift", "gifting", "উপহার", "গিফট"),
        "formal": ("formal", "ফরমাল"),
        "summer": ("summer", "lightweight", "light weight", "হালকা", "গরমে", "সামার"),
    }
    STYLE_ALIASES: dict[str, tuple[str, ...]] = {
        "lightweight": ("lightweight", "light weight", "soft", "comfortable", "halka", "হালকা", "আরামদায়ক", "আরামদায়ক"),
        "heavy": ("heavy", "heavily worked", "ভারি", "ভারী"),
        "simple": ("simple", "minimal", "plain", "সিম্পল", "সাধারণ"),
        "formal": ("formal", "ফরমাল"),
        "casual": ("casual", "ক্যাজুয়াল", "ক্যাজুয়াল"),
        "comfortable": ("comfortable", "comfort", "আরামদায়ক", "আরামদায়ক"),
        "premium": ("premium", "elegant", "festive", "dressy", "classy", "gorgeous", "এলিগেন্ট", "উৎসব"),
    }
    STYLE_ITEM_ALIASES: dict[str, tuple[str, ...]] = {
        "lightweight": ("lightweight", "light weight", "soft", "comfortable", "muslin"),
        "heavy": ("heavy", "bridal", "zari", "meena", "katan"),
        "simple": ("simple", "minimal", "plain", "office", "daily"),
        "formal": ("formal", "office", "interview"),
        "casual": ("casual", "daily", "college"),
        "comfortable": ("comfortable", "comfort", "flat", "sneaker"),
        "premium": ("premium", "party", "wedding", "eid", "jamdani", "katan", "buti", "zari", "meena", "silk", "georgette", "semi-formal"),
    }
    GENDER_ALIASES: dict[str, tuple[str, ...]] = {
        "men": (
            "men",
            "mens",
            "men's",
            "male",
            "gents",
            "gentleman",
            "chele",
            "cheleder",
            "boys",
            "পুরুষ",
            "ছেলে",
            "ছেলেদের",
            "জেন্টস",
        ),
        "women": (
            "women",
            "womens",
            "women's",
            "female",
            "ladies",
            "lady",
            "meyeder",
            "mohila",
            "নারী",
            "মহিলা",
            "মেয়েদের",
            "মেয়েদের",
            "লেডিস",
        ),
        "unisex": ("unisex", "সবার", "ইউনিসেক্স"),
    }
    VARIANT_PHRASES = (
        "same design",
        "same pattern",
        "same model",
        "same one",
        "same design ta",
        "same design e",
        "ekoi design",
        "ek design",
        "same colour e",
        "same color e",
        "another color",
        "other color",
        "onno color",
        "onnno color",
        "ar ek color",
        "arek color",
        "different color",
        "different colour",
        "other colour",
        "same design in",
        "same item in",
        "একই ডিজাইন",
        "এক ডিজাইন",
        "এই ডিজাইন",
        "একই প্যাটার্ন",
        "অন্য রঙ",
        "অন্য কালার",
        "আরেক কালার",
        "আরেক রঙ",
        "ভিন্ন রঙ",
    )
    ACCESSORY_MATCH_PHRASES = (
        "match",
        "matches",
        "matching",
        "go with",
        "goes with",
        "pair with",
        "pair korbo",
        "pair korle",
        "manabe",
        "manay",
        "sathe",
        "shathe",
        "sathe ki",
        "accessory",
        "accessories",
        "ম্যাচ",
        "ম্যাচিং",
        "মানাবে",
        "মানায়",
        "সাথে",
        "সঙ্গে",
        "যাবে",
    )
    AVAILABILITY_PHRASES = (
        "do you have",
        "have",
        "available",
        "in stock",
        "stock ache",
        "stock ase",
        "stock e ache",
        "ache",
        "ase",
        "available ache",
        "pawa jabe",
        "is there",
        "আছে",
        "স্টকে আছে",
        "স্টক আছে",
        "পাওয়া যাবে",
        "পাওয়া যাবে",
        "এভেইলেবল",
        "অ্যাভেইলেবল",
        "হবে",
    )
    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "available",
        "can",
        "color",
        "colour",
        "design",
        "different",
        "do",
        "for",
        "have",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "other",
        "same",
        "show",
        "size",
        "the",
        "this",
        "to",
        "under",
        "want",
        "with",
        "you",
        "amar",
        "ami",
        "ache",
        "ase",
        "eta",
        "ei",
        "ki",
        "kintu",
        "lagbe",
        "jonno",
        "দেখান",
        "দেখান",
        "দেখাও",
        "আছে",
        "কি",
        "কী",
        "আমার",
        "আমি",
        "এই",
        "ওই",
        "টা",
        "টি",
        "এর",
        "জন্য",
        "মধ্যে",
        "টাকার",
        "রঙ",
        "কালার",
        "ডিজাইন",
        "juta",
        "juto",
        "ghori",
        "shart",
        "shirt",
        "pant",
        "perfume",
        "lipstick",
        "sunscreen",
    }
    SIZE_PATTERN = re.compile(
        r"(?:size|sz|measurement|chest|waist|shoe size|সাইজ|মাপ|চেস্ট|কোমর)\s*[:#-]?\s*([a-z]{1,3}|\d{1,2}(?:\.\d)?|100ml|50ml)\b",
        re.IGNORECASE,
    )
    REVERSE_SIZE_PATTERN = re.compile(
        r"\b([a-z]{1,3}|\d{1,2}(?:\.\d)?|100ml|50ml)\s*(?:size|sz|waist|ml|সাইজ|মাপ|কোমর)\b",
        re.IGNORECASE,
    )
    BARE_SIZE_PATTERN = re.compile(r"\b([2-5]\d|2\.[2468]|3\.[02468]|xs|s|m|l|xl|xxl|xxxl|100ml|50ml)\b", re.IGNORECASE)
    MAX_PRICE_PATTERN = re.compile(
        r"(?:under|below|less than|within|up to|max|maximum|budget|around|about|কম|নিচে|মধ্যে|বাজেট)\s*(?:bdt|tk|taka|টাকা|টাকার|৳)?\s*(\d+(?:\.\d+)?)|(?:bdt|tk|taka|টাকা|টাকার|৳)?\s*(\d+(?:\.\d+)?)\s*(?:taka|tk|bdt|টাকা|টাকার)?\s*(?:er modhe|er moddhe|modhe|moddhe|within|এর মধ্যে|মধ্যে|ভিতরে)",
        re.IGNORECASE,
    )
    MIN_PRICE_PATTERN = re.compile(
        r"(?:over|above|more than|at least|min|minimum)\s*(?:bdt|tk|taka|৳)?\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    def answer(
        self,
        *,
        question: str,
        catalog: dict[str, InventoryItemRecord],
        filters: InventorySearchFilters | None = None,
        focused_product_ids: tuple[str, ...] = (),
        last_primary_product_id: str | None = None,
        top_k: int = 5,
        conversation_history: list[tuple[str, str]] | None = None,
        allow_llm_slots: bool = True,
    ) -> FashionRetailOutcome | None:
        filters = filters or InventorySearchFilters()
        fashion_items = [item for item in catalog.values() if self.is_fashion_item(item)]
        if not fashion_items:
            return None

        # Carry prior turns only for true follow-up language ("same design",
        # "eta", "tar dam"). If the current message names a fresh category,
        # budget, occasion, or gender, old context must not override it.
        use_context = self._should_use_conversation_context(question)
        enriched_question = self._enrich_with_history(question, conversation_history) if use_context else question
        effective_focused_product_ids = focused_product_ids if use_context else ()
        effective_last_primary_product_id = last_primary_product_id if use_context else None

        slots = self.extract_slots(
            question=enriched_question,
            filters=filters,
            catalog=fashion_items,
            focused_product_ids=effective_focused_product_ids,
            last_primary_product_id=effective_last_primary_product_id,
            allow_llm=allow_llm_slots,
        )
        if not self.should_handle(question=question, slots=slots, fashion_items=fashion_items):
            return None

        # Clarification gate — runs once, before dispatching to intent handlers.
        # If the bot is uncertain or the query is too broad, ask one focused
        # question instead of dumping a wide product list.
        clarification = self._maybe_clarify(slots=slots, items=fashion_items)
        if clarification is not None:
            return clarification

        if slots.intent == "fashion_styling_advice":
            outcome = self._answer_styling_advice(question=question, items=fashion_items, slots=slots, top_k=top_k)
            if outcome is not None:
                return outcome

        if slots.intent == "fashion_multi_brand_clarification":
            outcome = self._answer_multi_brand_clarification(question=question, items=fashion_items, slots=slots, top_k=top_k)
            if outcome is not None:
                return outcome

        if slots.intent == "fashion_variant_color":
            outcome = self._answer_variant_color(question=question, items=fashion_items, slots=slots, top_k=top_k)
            if outcome is not None:
                return outcome

        if slots.intent == "fashion_size_availability":
            outcome = self._answer_size_availability(question=question, items=fashion_items, slots=slots, top_k=top_k)
            if outcome is not None:
                return outcome

        if slots.intent == "fashion_accessory_match":
            outcome = self._answer_accessory_match(question=question, items=fashion_items, slots=slots, top_k=top_k)
            if outcome is not None:
                return outcome

        if slots.intent == "fashion_compare":
            outcome = self._answer_fashion_compare(question=question, items=fashion_items, slots=slots, top_k=top_k)
            if outcome is not None:
                return outcome

        return self._answer_fashion_search(question=question, items=fashion_items, slots=slots, top_k=top_k)

    def _should_use_conversation_context(self, question: str) -> bool:
        text = normalize_fashion_text(question)
        if not text:
            return False
        if self._extract_category_key(text=text, filters=InventorySearchFilters()):
            return False
        if self._extract_budget(question) != (None, None):
            return False
        if self._extract_alias(text, self.OCCASION_ALIASES):
            return False
        if self._extract_alias(text, self.FABRIC_ALIASES):
            return False
        if self._extract_alias(text, self.WORK_ALIASES):
            return False
        if self._extract_gender(text):
            return False
        if self._extract_color(text)[1] and not any(self._contains_phrase(text, phrase) for phrase in self.VARIANT_PHRASES):
            return False
        follow_up_terms = (
            "eta",
            "eita",
            "eitai",
            "otar",
            "oita",
            "oi",
            "tar",
            "er dam",
            "price",
            "dam",
            "same design",
            "same color",
            "same colour",
            "another color",
            "other color",
            "first one",
            "second one",
            "previous",
            "this one",
            "that one",
            "এটা",
            "ওটা",
            "তার",
            "দাম",
            "একই ডিজাইন",
            "অন্য রঙ",
        )
        return any(self._contains_phrase(text, term) for term in follow_up_terms)

    def should_handle(
        self,
        *,
        question: str,
        slots: FashionRetailSlots,
        fashion_items: list[InventoryItemRecord],
    ) -> bool:
        text = normalize_fashion_text(question)
        if slots.category_key and slots.category_key in self.CATEGORY_LABELS:
            return True
        if slots.intent in {"fashion_variant_color", "fashion_size_availability", "fashion_accessory_match"}:
            return True
        if slots.fabric or slots.work_type:
            return True
        if any(self._contains_phrase(text, alias) for aliases in self.CATEGORY_ALIASES.values() for alias in aliases):
            if self._has_tech_context_without_fashion_context(text):
                return False
            return True
        if slots.color_family and any(
            self._contains_phrase(text, term)
            for term in (
                "saree",
                "blouse",
                "panjabi",
                "three piece",
                "jewelry",
                "clutch",
                "bag",
                "shoe",
                "watch",
                "shirt",
                "pant",
                "perfume",
                "lipstick",
            )
        ):
            return True
        return False

    def extract_slots(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        catalog: list[InventoryItemRecord],
        focused_product_ids: tuple[str, ...] = (),
        last_primary_product_id: str | None = None,
        allow_llm: bool = True,
    ) -> FashionRetailSlots:
        # Banglish augmentation + fuzzy typo correction, then normalize
        augmented_question = augment_with_bangla(question)
        augmented_question = augment_with_corrections(augmented_question)
        text = normalize_fashion_text(augmented_question)
        evidence: list[str] = []
        language = self._detect_language(question)
        if language != "english":
            evidence.append(f"language:{language}")
        category_key = self._extract_category_key(text=text, filters=filters)
        if category_key:
            evidence.append(f"category:{category_key}")
        color, color_family = self._extract_color(text)
        if color_family:
            evidence.append(f"color:{color or color_family}")
        size = self._extract_size(text=text, category_key=category_key)
        if size:
            evidence.append(f"size:{size}")
        budget_min, budget_max = self._extract_budget(question)
        if filters.min_price is not None:
            budget_min = filters.min_price
        if filters.max_price is not None:
            budget_max = filters.max_price
        if budget_min is not None:
            evidence.append(f"budget_min:{budget_min}")
        if budget_max is not None:
            evidence.append(f"budget_max:{budget_max}")
        fabric = self._extract_alias(text, self.FABRIC_ALIASES)
        if fabric:
            evidence.append(f"fabric:{fabric}")
        work_type = self._extract_alias(text, self.WORK_ALIASES)
        if work_type:
            evidence.append(f"work_type:{work_type}")
        occasion = self._extract_alias(text, self.OCCASION_ALIASES)
        if occasion:
            evidence.append(f"occasion:{occasion}")
        style = self._extract_alias(text, self.STYLE_ALIASES)
        if style:
            evidence.append(f"style:{style}")
        gender = self._extract_gender(text)
        if gender:
            evidence.append(f"gender:{gender}")
        wants_in_stock = bool(filters.min_stock and filters.min_stock > 0) or any(
            self._contains_phrase(text, phrase) for phrase in self.AVAILABILITY_PHRASES
        )

        design_id = self._resolve_design_id(
            question=question,
            items=catalog,
            focused_product_ids=focused_product_ids,
            last_primary_product_id=last_primary_product_id,
        )
        if design_id and category_key:
            variants = self._same_design_items(catalog, design_id)
            if variants and not any(self._item_category_matches(item, category_key) for item in variants):
                design_id = None
        if design_id:
            evidence.append(f"design_id:{design_id}")
        intent = self._classify_intent(
            text=text,
            category_key=category_key,
            color_family=color_family,
            size=size,
            design_id=design_id,
        )
        regex_slots = FashionRetailSlots(
            category_key=category_key,
            category_label=self.CATEGORY_LABELS.get(category_key) if category_key else None,
            color=color,
            color_family=color_family,
            size=size,
            budget_min=budget_min,
            budget_max=budget_max,
            fabric=fabric,
            work_type=work_type,
            occasion=occasion,
            style=style,
            gender=gender,
            design_id=design_id,
            wants_in_stock=wants_in_stock,
            intent=intent,
            language=language,
            evidence=tuple(evidence),
            confidence=self._estimate_regex_confidence(
                category_key=category_key,
                color_family=color_family,
                fabric=fabric,
                size=size,
                occasion=occasion,
                budget_max=budget_max,
            ),
        )
        # LLM-first path: classify intent + slots + confidence in one call.
        # Regex result acts as a safety net for fields the LLM left null.
        if allow_llm and is_ollama_available():
            classified = classify_intent_llm(question)
            if classified is not None:
                return self._merge_classified_with_regex(
                    classified=classified,
                    regex_slots=regex_slots,
                )
        return regex_slots

    @staticmethod
    def _enrich_with_history(
        question: str,
        history: list[tuple[str, str]] | None,
        max_turns: int = 3,
    ) -> str:
        """
        Prepend the last `max_turns` user messages to the current question so
        slot extraction can carry over category/color/fabric from prior turns.
        E.g. "এটার দাম কত?" after "লাল জামদানি শাড়ি দেখাও" will inherit
        category=saree, color=red, fabric=jamdani.
        """
        if not history:
            return question
        user_turns = [content for role, content in history if role == "user"]
        prior = " | ".join(user_turns[-max_turns:])
        return f"{prior} | {question}"

    @staticmethod
    def _estimate_regex_confidence(
        *,
        category_key: str | None,
        color_family: str | None,
        fabric: str | None,
        size: str | None,
        occasion: str | None,
        budget_max: float | None,
    ) -> float:
        """
        When LLM is unavailable, derive a confidence proxy from how many
        concrete slots regex managed to extract. Used to decide between
        answering and asking a clarifying question downstream.
        """
        slots_present = sum(
            1 for v in (category_key, color_family, fabric, size, occasion, budget_max)
            if v is not None
        )
        if slots_present >= 3:
            return 0.92
        if slots_present == 2:
            return 0.82
        if slots_present == 1:
            return 0.68
        return 0.42

    def _merge_classified_with_regex(
        self,
        *,
        classified: ClassifiedIntent,
        regex_slots: FashionRetailSlots,
    ) -> FashionRetailSlots:
        """
        Combine LLM classification (which provides intent + confidence + most slots)
        with regex extraction (more reliable for color_family normalization,
        category_key canonicalisation, design_id resolution, evidence trail).

        Strategy:
          - Intent: prefer LLM unless LLM said "unknown" or confidence is very low.
          - Slots: regex wins when set (it understands the canonical aliases),
            LLM fills gaps.
          - Confidence: take LLM's score, but never below regex-implied confidence.
          - Evidence: regex evidence + LLM marker.
        """
        # Map LLM category to regex canonical key when regex missed it
        llm_category_key = classified.category if classified.category in self.CATEGORY_LABELS else None
        category_key = regex_slots.category_key or llm_category_key
        category_label = (
            self.CATEGORY_LABELS.get(category_key) if category_key else regex_slots.category_label
        )

        # Color: regex computes color_family + canonical color; only adopt LLM color
        # when regex got nothing.
        color = regex_slots.color or classified.color
        color_family = regex_slots.color_family
        if not color_family and classified.color:
            color_family = self._color_family_for(classified.color)

        # Intent selection — only adopt LLM intent if it's a fashion-domain or
        # known boutique intent and the model was reasonably confident.
        intent = regex_slots.intent
        if classified.intent not in {"unknown", "smalltalk"} and classified.confidence >= 0.55:
            intent = classified.intent

        # Confidence: trust the LLM's semantic score. The regex proxy is a
        # fallback for when the LLM isn't available — combining them via max
        # would suppress the LLM's "I'm uncertain" signal whenever regex finds
        # any slot, defeating the clarification gate.
        confidence = classified.confidence

        evidence = regex_slots.evidence + (
            f"llm_intent:{classified.intent}",
            f"llm_confidence:{classified.confidence:.2f}",
        )

        return FashionRetailSlots(
            category_key=category_key,
            category_label=category_label,
            color=color,
            color_family=color_family,
            size=regex_slots.size or classified.size,
            budget_min=regex_slots.budget_min if regex_slots.budget_min is not None else classified.budget_min,
            budget_max=regex_slots.budget_max if regex_slots.budget_max is not None else classified.budget_max,
            fabric=regex_slots.fabric or classified.fabric,
            work_type=regex_slots.work_type or classified.work_type,
            occasion=regex_slots.occasion or classified.occasion,
            style=regex_slots.style,
            gender=regex_slots.gender,
            design_id=regex_slots.design_id,
            wants_in_stock=regex_slots.wants_in_stock or classified.wants_in_stock,
            intent=intent,
            language=regex_slots.language if regex_slots.language != "english" else classified.language,
            evidence=evidence,
            confidence=confidence,
            ambiguity_reason=classified.ambiguity_reason,
        )

    def _maybe_clarify(
        self,
        *,
        slots: FashionRetailSlots,
        items: list[InventoryItemRecord],
    ) -> FashionRetailOutcome | None:
        """
        Run the clarification policy. Return a clarification outcome to short
        circuit the answer flow, or None to proceed with the normal handler.

        Skip clarification when:
          - the customer already pinned a specific design (design_id)
          - the intent is variant/size/accessory/compare/styling — those are
            already focused, asking again would be annoying
          - the intent is policy or order — those have dedicated handlers
        """
        from app.inventory.clarification import decide_clarification

        if slots.design_id:
            return None
        if slots.intent in {
            "fashion_variant_color",
            "fashion_size_availability",
            "fashion_accessory_match",
            "fashion_compare",
            "fashion_styling_advice",
            "fashion_multi_brand_clarification",
        }:
            return None

        # Estimate match count cheaply using category + color filter
        match_count = self._estimate_match_count(slots=slots, items=items)
        decision = decide_clarification(slots=slots, total_matches=match_count)
        if not decision.should_clarify:
            return None

        return FashionRetailOutcome(
            answer=decision.question or "",
            intent="fashion_clarification",
            product_ids=(),
            cross_sell_product_ids=(),
            total_matches=match_count,
            confidence=slots.confidence,
            slots=slots,
            follow_up_question=decision.question,
            abstained=False,
            abstention_reason=None,
            reasoning_steps=(
                f"Clarification triggered: {decision.reason}",
                f"Missing slot: {decision.missing_slot}",
            ),
        )

    def _estimate_match_count(
        self,
        *,
        slots: FashionRetailSlots,
        items: list[InventoryItemRecord],
    ) -> int:
        """
        Cheap pre-flight count: how many items the current slots would match.
        Used only by the clarification gate — not the answer ranker.
        """
        count = 0
        for item in items:
            if slots.category_key and not self._item_category_matches(item, slots.category_key):
                continue
            if slots.color_family:
                item_color = normalize_fashion_text(
                    item.attributes.get("color_family") or item.attributes.get("color") or ""
                )
                if item_color and slots.color_family not in item_color:
                    continue
            if slots.fabric:
                item_fabric = normalize_fashion_text(item.attributes.get("fabric", ""))
                if item_fabric and slots.fabric not in item_fabric:
                    continue
            count += 1
        return count

    def _color_family_for(self, color: str | None) -> str | None:
        """Lookup canonical color family for an LLM-supplied color name."""
        if not color:
            return None
        token = normalize_fashion_text(color)
        for canonical_key, (_canonical, family, aliases) in self.COLOR_ALIASES.items():
            if token == normalize_fashion_text(canonical_key):
                return family
            if any(token == normalize_fashion_text(a) for a in aliases):
                return family
        return None

    def is_fashion_item(self, item: InventoryItemRecord) -> bool:
        category_text = normalize_fashion_text(item.category)
        item_text = self._item_text(item)
        if any(self._contains_phrase(category_text, term) for term in self.ITEM_FASHION_CATEGORY_TERMS):
            return True
        source = normalize_fashion_text(item.metadata.get("source"))
        if "saree" in source or "fashion" in source or "boutique" in source or "aarong" in source:
            return True
        if self._canonical_category_key(item.attributes.get("category_key")):
            return True
        if item.attributes.get("design_id") and any(
            key in item.attributes
            for key in (
                "fabric",
                "work_type",
                "color",
                "size",
                "compatible_design_ids",
                "accessory_type",
                "skin_type",
                "fragrance_family",
                "shoe_type",
                "watch_type",
            )
        ):
            return True
        if item.attributes.get("accessory_type") or item.attributes.get("compatible_design_ids"):
            return True
        if category_text == "accessories":
            return any(self._contains_phrase(item_text, term) for term in self.ITEM_FASHION_CATEGORY_TERMS - {"bag"})
        return False

    def _answer_variant_color(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> FashionRetailOutcome | None:
        if not slots.design_id:
            return None
        variants = self._same_design_items(items, slots.design_id)
        if not variants:
            return None
        if not slots.color_family:
            in_stock = [item for item in variants if item.stock > 0]
            if not in_stock:
                return self._outcome(
                    answer="I found that design family, but all listed color variants are currently out of stock.",
                    intent=slots.intent,
                    product_ids=tuple(item.product_id for item in variants[:top_k]),
                    total_matches=len(variants),
                    confidence=0.78,
                    slots=slots,
                    abstained=False,
                    reasoning_steps=("Resolved the design family, then checked stock across color variants.",),
                )
            answer = f"Yes. In that same design, available colors are {self._color_stock_list(in_stock)}."
            out_stock = [item for item in variants if item.stock <= 0]
            if out_stock:
                answer += f" Out-of-stock colors: {self._color_stock_list(out_stock, include_stock=False)}."
            return self._outcome(
                answer=answer,
                intent=slots.intent,
                product_ids=tuple(item.product_id for item in in_stock[:top_k]),
                total_matches=len(variants),
                confidence=0.88,
                slots=slots,
                reasoning_steps=("Resolved the design family, then listed available color variants.",),
            )

        exact_color = [item for item in variants if self._item_color_matches(item, slots.color_family, slots.color)]
        if exact_color:
            exact_color = sorted(exact_color, key=lambda item: (-item.stock, self._item_price_value(item), item.name.casefold()))
            best = exact_color[0]
            alternatives = [item for item in variants if item.product_id != best.product_id and item.stock > 0]
            if best.stock > 0:
                answer = f"Yes. {best.name} is available: {self._format_price(best)}, {best.stock} in stock."
                if alternatives:
                    answer += f" Other in-stock colors in the same design: {self._color_stock_list(alternatives)}."
                return self._outcome(
                    answer=answer,
                    intent=slots.intent,
                    product_ids=tuple(item.product_id for item in [best, *alternatives[: top_k - 1]]),
                    total_matches=len(variants),
                    confidence=0.95,
                    slots=slots,
                    reasoning_steps=("Matched requested color inside the same design_id and checked stock.",),
                )
            in_stock = [item for item in variants if item.stock > 0]
            answer = f"We have {best.name} in that same design, but it is currently out of stock."
            if in_stock:
                answer += f" In-stock colors in the same design: {self._color_stock_list(in_stock)}."
            else:
                answer += " No other colors in this design are in stock right now."
            return self._outcome(
                answer=answer,
                intent=slots.intent,
                product_ids=tuple(item.product_id for item in [best, *in_stock[: top_k - 1]]),
                total_matches=len(variants),
                confidence=0.93,
                slots=slots,
                reasoning_steps=("Matched requested color inside the same design_id and found stock is zero.",),
            )

        in_stock = [item for item in variants if item.stock > 0]
        requested = slots.color or slots.color_family or "that color"
        answer = f"I do not see {requested} in that exact design."
        if in_stock:
            answer += f" In-stock colors in the same design are {self._color_stock_list(in_stock)}."
        return self._outcome(
            answer=answer,
            intent=slots.intent,
            product_ids=tuple(item.product_id for item in in_stock[:top_k]),
            total_matches=len(variants),
            confidence=0.86,
            slots=slots,
            reasoning_steps=("Resolved the design family but found no variant matching the requested color.",),
        )

    def _answer_size_availability(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> FashionRetailOutcome | None:
        if not slots.size:
            return None
        candidates = [
            item
            for item in items
            if self._item_matches_search_slots(item, slots, strict_size=True, strict_color=bool(slots.color_family))
        ]
        exact = [item for item in candidates if self._item_size_matches(item, slots.size)]
        if not exact:
            exact = [
                item
                for item in items
                if self._item_size_matches(item, slots.size)
                and (not slots.category_key or self._item_category_matches(item, slots.category_key))
                and (not slots.color_family or self._item_color_matches(item, slots.color_family, slots.color))
            ]
        exact = sorted(exact, key=lambda item: (-item.stock, self._item_price_value(item), item.name.casefold()))
        if exact:
            best = exact[0]
            if best.stock > 0:
                answer = f"Yes. {best.name} is available in size {slots.size}: {self._format_price(best)}, {best.stock} in stock."
                return self._outcome(
                    answer=answer,
                    intent=slots.intent,
                    product_ids=tuple(item.product_id for item in exact[:top_k]),
                    total_matches=len(exact),
                    confidence=0.95,
                    slots=slots,
                    reasoning_steps=("Matched the requested size as a structured attribute before semantic ranking.",),
                )
            alternatives = self._same_design_or_category_alternatives(best, items, slots)
            answer = f"Size {slots.size} for {best.name} is currently out of stock."
            if alternatives:
                answer += f" Closest available option: {self._format_option(alternatives[0])}."
            return self._outcome(
                answer=answer,
                intent=slots.intent,
                product_ids=tuple(item.product_id for item in [best, *alternatives[: top_k - 1]]),
                total_matches=len(exact),
                confidence=0.94,
                slots=slots,
                reasoning_steps=("Matched the requested size exactly and found stock is zero.",),
            )

        search_matches = self._rank_search_items(question=question, items=items, slots=slots, top_k=top_k)
        answer = f"I do not see size {slots.size} in the current catalog for that request."
        if search_matches:
            available_sizes = self._available_size_list([match.item for match in search_matches])
            if available_sizes:
                answer += f" Available nearby sizes I can see: {available_sizes}."
        return self._outcome(
            answer=answer,
            intent=slots.intent,
            product_ids=tuple(match.item.product_id for match in search_matches),
            total_matches=len(search_matches),
            confidence=0.82,
            slots=slots,
            reasoning_steps=("Checked structured size fields and did not find the requested size.",),
        )

    def _answer_accessory_match(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> FashionRetailOutcome | None:
        design_id = slots.design_id
        requested_accessory_keys = self._extract_requested_accessory_keys(normalize_fashion_text(question))
        anchor_slots = slots
        if slots.category_key in {"accessories", *requested_accessory_keys} or (
            slots.category_key and self._is_accessory_category(slots.category_key)
        ):
            anchor_slots = replace(slots, category_key=None, category_label=None)
        anchor = self._resolve_anchor_item(question=question, items=items, slots=anchor_slots)
        if anchor and not design_id:
            design_id = self._item_design_id(anchor)
        scored: list[_ScoredItem] = []
        for item in items:
            if anchor and item.product_id == anchor.product_id:
                continue
            if not self._is_accessory_item(item):
                continue
            if requested_accessory_keys and not any(self._item_category_matches(item, key) for key in requested_accessory_keys):
                continue
            if slots.gender and not self._item_gender_matches(item, slots.gender):
                continue
            score = 0.0
            reasons: list[str] = []
            compatible_design_ids = self._split_multi_value(item.attributes.get("compatible_design_ids"))
            compatible_design_ids.extend(self._split_multi_value(item.metadata.get("compatible_design_ids")))
            if design_id and design_id in compatible_design_ids:
                score += 5.0
                reasons.append("compatible_design_id")
            if anchor is not None:
                anchor_color_family = self._item_color_family(anchor)
                compatible_colors = self._split_multi_value(item.attributes.get("compatible_colors"))
                if anchor_color_family and any(self._color_value_matches(value, anchor_color_family, None) for value in compatible_colors):
                    score += 1.5
                    reasons.append("compatible_color")
            if item.stock > 0:
                score += 0.7
            score += min(self._lexical_overlap_score(question, self._item_text(item)), 2.0)
            if score > 0.75:
                scored.append(_ScoredItem(item=item, score=score, reasons=tuple(reasons)))
        scored = sorted(scored, key=lambda match: (-match.score, -match.item.stock, self._item_price_value(match.item), match.item.name.casefold()))
        selected = scored[:top_k]
        if selected:
            anchor_phrase = f" for {anchor.name}" if anchor else ""
            requested_label = (
                f"{self._accessory_match_label(requested_accessory_keys[0])} "
                if len(requested_accessory_keys) == 1 and requested_accessory_keys[0] in self.CATEGORY_LABELS
                else ""
            )
            answer = f"Good {requested_label}matches{anchor_phrase}: {self._natural_join(self._format_option(match.item) for match in selected[:3])}."
            return self._outcome(
                answer=answer,
                intent=slots.intent,
                product_ids=tuple(match.item.product_id for match in selected),
                cross_sell_product_ids=tuple(match.item.product_id for match in selected),
                total_matches=len(scored),
                confidence=0.9 if any("compatible_design_id" in match.reasons for match in selected) else 0.78,
                slots=slots,
                reasoning_steps=("Resolved product/design context and ranked accessories by compatibility metadata first.",),
            )
        return None

    def _answer_fashion_search(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> FashionRetailOutcome:
        scored = self._rank_search_items(question=question, items=items, slots=slots, top_k=max(top_k, 5))
        relaxed_reason: str | None = None
        if not scored:
            relaxed_slots, relaxed_reason = self._first_relaxed_search_match(
                question=question,
                items=items,
                slots=slots,
                top_k=max(top_k, 5),
            )
            if relaxed_slots is not None:
                scored = self._rank_search_items(question=question, items=items, slots=relaxed_slots, top_k=max(top_k, 5))

        # Semantic fallback: after deterministic relaxation still finds
        # nothing, ask the embedding matcher. Catches novel vocabulary the
        # regex layer could not parse.
        semantic_used = False
        if not scored:
            try:
                from app.inventory.semantic_matcher import get_semantic_matcher
                catalog_dict = {item.product_id: item for item in items}
                matcher = get_semantic_matcher()
                semantic_results = matcher.retrieve(
                    question=question, catalog=catalog_dict, top_k=max(top_k, 5),
                )
                if semantic_results:
                    item_by_id = {it.product_id: it for it in items}
                    for sm in semantic_results:
                        item = item_by_id.get(sm.product_id)
                        if item is None:
                            continue
                        scored.append(_ScoredItem(
                            item=item,
                            score=sm.score,
                            reasons=("semantic_match",),
                        ))
                    semantic_used = bool(scored)
            except Exception:
                pass

        if not scored:
            category = slots.category_label.lower() if slots.category_label else "fashion product"
            answer = f"I could not find an exact in-catalog {category} for those details yet."
            follow_up = "Tell me the category, color, size, budget, or occasion and I can narrow it down."
            return self._outcome(
                answer=answer,
                intent=slots.intent,
                product_ids=(),
                total_matches=0,
                confidence=0.72,
                slots=slots,
                follow_up_question=follow_up,
                abstained=True,
                abstention_reason="No fashion catalog item matched the extracted structured slots.",
                reasoning_steps=("Applied structured fashion filters before semantic fallback and found no eligible item.",),
            )

        selected = [match.item for match in scored[:top_k]]
        if len(selected) == 1:
            answer = f"Yes — {self._format_option(selected[0])}."
        else:
            if relaxed_reason:
                answer = (
                    f"I don't have an exact {relaxed_reason}; closest available options are: "
                    f"{self._natural_join(self._format_option(item) for item in selected[:3])}."
                )
            else:
                first_pick = self._format_option(selected[0])
                answer = (
                    f"I have a few good options: "
                    f"{self._natural_join(self._format_option(item) for item in selected[:3])}. "
                    f"My first pick would be {first_pick}."
                )
        reasoning_step = (
            "Semantic fallback retrieved candidates after slot filter found nothing."
            if semantic_used
            else f"Relaxed filters after exact search had no match: {relaxed_reason}."
            if relaxed_reason
            else "Extracted fashion slots and ranked matching catalog items with stock and exact attributes ahead of fuzzy text."
        )
        return self._outcome(
            answer=answer,
            intent=slots.intent,
            product_ids=tuple(item.product_id for item in selected),
            total_matches=len(scored),
            confidence=(0.74 if semantic_used else 0.86) if selected[0].stock > 0 else (0.62 if semantic_used else 0.76),
            slots=slots,
            follow_up_question="Should I narrow this by color, size, fabric, budget, or occasion?",
            reasoning_steps=(reasoning_step,),
        )

    def _first_relaxed_search_match(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> tuple[FashionRetailSlots | None, str | None]:
        candidates: list[tuple[FashionRetailSlots, str]] = []
        if slots.style:
            candidates.append((replace(slots, style=None), f"{slots.style} style {slots.category_label or 'item'}"))
        if slots.occasion:
            candidates.append((replace(slots, occasion=None), f"{slots.occasion} {slots.category_label or 'item'}"))
        if slots.fabric:
            candidates.append((replace(slots, fabric=None), f"{slots.fabric} {slots.category_label or 'item'}"))
        if slots.work_type:
            candidates.append((replace(slots, work_type=None), f"{slots.work_type} work {slots.category_label or 'item'}"))
        if slots.budget_max is not None and any((slots.occasion, slots.style, slots.fabric, slots.work_type)):
            candidates.append((
                replace(slots, occasion=None, style=None, fabric=None, work_type=None),
                f"occasion/style matching {slots.category_label or 'item'} under BDT {slots.budget_max:,.0f}",
            ))
        if slots.budget_max is not None:
            candidates.append((replace(slots, budget_max=None), f"under BDT {slots.budget_max:,.0f} {slots.category_label or 'item'}"))
        if slots.category_key:
            candidates.append((
                replace(slots, color=None, color_family=None, size=None, occasion=None, style=None, fabric=None, work_type=None, budget_min=None, budget_max=None),
                f"fully matching {slots.category_label or slots.category_key}",
            ))

        seen: set[tuple[Any, ...]] = set()
        for candidate_slots, reason in candidates:
            marker = (
                candidate_slots.category_key,
                candidate_slots.color_family,
                candidate_slots.size,
                candidate_slots.occasion,
                candidate_slots.style,
                candidate_slots.fabric,
                candidate_slots.work_type,
                candidate_slots.budget_min,
                candidate_slots.budget_max,
                candidate_slots.gender,
            )
            if marker in seen:
                continue
            seen.add(marker)
            if self._rank_search_items(question=question, items=items, slots=candidate_slots, top_k=top_k):
                return candidate_slots, reason
        return None, None

    def _rank_search_items(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> list[_ScoredItem]:
        scored: list[_ScoredItem] = []
        for item in items:
            if not self._item_matches_search_slots(item, slots):
                continue
            score, reasons = self._score_search_item(question=question, item=item, slots=slots)
            if score > 0:
                scored.append(_ScoredItem(item=item, score=score, reasons=tuple(reasons)))
        return sorted(scored, key=lambda match: (-match.score, -match.item.stock, self._item_price_value(match.item), match.item.name.casefold()))[:top_k]

    def _item_matches_search_slots(
        self,
        item: InventoryItemRecord,
        slots: FashionRetailSlots,
        *,
        strict_size: bool = False,
        strict_color: bool = False,
    ) -> bool:
        if slots.category_key and not self._item_category_matches(item, slots.category_key):
            return False
        if slots.gender and not self._item_gender_matches(item, slots.gender):
            return False
        if slots.color_family and (strict_color or slots.intent in {"fashion_search", "fashion_size_availability"}):
            if not self._item_color_matches(item, slots.color_family, slots.color):
                return False
        if slots.size and strict_size and not self._item_size_matches(item, slots.size):
            return False
        if slots.budget_min is not None and (item.price is None or item.price < slots.budget_min):
            return False
        if slots.budget_max is not None and (item.price is None or item.price > slots.budget_max):
            return False
        if slots.fabric and not self._contains_phrase(self._item_text(item), slots.fabric):
            return False
        if slots.work_type and not self._contains_phrase(self._item_text(item), slots.work_type):
            return False
        if slots.occasion and not self._contains_phrase(self._item_text(item), slots.occasion):
            return False
        if slots.style and not self._item_style_matches(item, slots.style):
            return False
        if slots.wants_in_stock and item.stock <= 0 and slots.intent != "fashion_variant_color":
            return False
        return True

    def _score_search_item(
        self,
        *,
        question: str,
        item: InventoryItemRecord,
        slots: FashionRetailSlots,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        if slots.category_key and self._item_category_matches(item, slots.category_key):
            score += 3.0
            reasons.append("category")
        if slots.color_family and self._item_color_matches(item, slots.color_family, slots.color):
            score += 3.0
            reasons.append("color")
        if slots.size and self._item_size_matches(item, slots.size):
            score += 4.0
            reasons.append("size")
        if slots.fabric and self._contains_phrase(self._item_text(item), slots.fabric):
            score += 2.0
            reasons.append("fabric")
        if slots.work_type and self._contains_phrase(self._item_text(item), slots.work_type):
            score += 1.5
            reasons.append("work_type")
        if slots.occasion and self._contains_phrase(self._item_text(item), slots.occasion):
            score += 1.5
            reasons.append("occasion")
        if slots.style and self._item_style_matches(item, slots.style):
            score += 2.0
            reasons.append("style")
        if slots.gender and self._item_gender_matches(item, slots.gender):
            score += 1.4
            reasons.append("gender")
        if slots.budget_max is not None and item.price is not None and item.price <= slots.budget_max:
            score += 1.2
            reasons.append("budget")
        if item.stock > 0:
            score += 0.8
            reasons.append("in_stock")
        lexical = self._lexical_overlap_score(question, self._item_text(item))
        score += lexical
        if lexical > 0:
            reasons.append("lexical")
        return score, reasons

    COMPARE_PHRASES = (
        " vs ", " vs. ", " versus ",
        " ar ", " and ", " ba ", " naki ",
        "difference between", "difference", "difference koto",
        "konta bhalo", "konta better", "konta nibo", "konta nebo",
        "compare", "comparison", "compared to",
        "কোনটা ভালো", "কোনটা নেব", "পার্থক্য", "তুলনা",
        "kontar dam beshi", "which one", "which is better",
        "er moddhe konta", "er maje konta",
        "prefer kori", "recommend korben",
    )

    STYLING_ADVICE_PHRASES = (
        "styling advice",
        "style suggestion",
        "what should i wear",
        "what goes with",
        "ki nile bhalo hobe",
        "ki nile valo hobe",
        "sathe ki manabe",
        "sathe ki nilam",
        "complete look",
        "outfit idea",
        "combination suggest",
        "look complete",
        "ki ki nebo",
        "ki ki nibo",
        "konta valo",
        "konta better",
        "better option",
        "ভালো হবে",
        "কী নিলে",
        "কী মানাবে",
        "কম্বিনেশন",
        "স্টাইল",
        "outfit",
    )
    BRAND_ALIASES: dict[str, tuple[str, ...]] = {
        "aarong": ("aarong", "arong", "arang", "আড়ং", "আড়োং"),
        "artisan": ("artisan", "artisan collection"),
        "richman": ("richman", "rich man"),
        "dorjibari": ("dorjibari", "dorji bari", "দর্জিবাড়ি"),
        "rang": ("rang", "rang bangladesh", "রং"),
        "yellow": ("yellow", "yellow fashion"),
        "ecstasy": ("ecstasy",),
        "sailor": ("sailor",),
    }

    def _classify_intent(
        self,
        *,
        text: str,
        category_key: str | None,
        color_family: str | None,
        size: str | None,
        design_id: str | None,
    ) -> str:
        if any(self._contains_phrase(text, phrase) for phrase in self.ACCESSORY_MATCH_PHRASES):
            if self._extract_requested_accessory_keys(text) or self._has_any_accessory_question_word(text):
                return "fashion_accessory_match"
        if any(self._contains_phrase(text, phrase) for phrase in self.STYLING_ADVICE_PHRASES):
            return "fashion_styling_advice"
        if any(phrase in text for phrase in self.COMPARE_PHRASES):
            return "fashion_compare"
        if size and any(self._contains_phrase(text, phrase) for phrase in self.AVAILABILITY_PHRASES):
            return "fashion_size_availability"
        if any(self._contains_phrase(text, phrase) for phrase in self.ACCESSORY_MATCH_PHRASES):
            return "fashion_accessory_match"
        if color_family and (design_id or any(self._contains_phrase(text, phrase) for phrase in self.VARIANT_PHRASES)):
            return "fashion_variant_color"
        if any(self._contains_phrase(text, phrase) for phrase in self.VARIANT_PHRASES):
            return "fashion_variant_color"
        if size:
            return "fashion_size_availability"
        return "fashion_search"

    def _extract_category_key(self, *, text: str, filters: InventorySearchFilters) -> str | None:
        for category in filters.categories:
            category_key = self._canonical_category_key(category)
            if category_key:
                return category_key
        for key, aliases in self.CATEGORY_ALIASES.items():
            if any(self._contains_phrase(text, alias) for alias in aliases):
                return key
        return None

    def _extract_requested_accessory_keys(self, text: str) -> tuple[str, ...]:
        requested: list[str] = []
        for key in ("bag", "jewelry", "perfume", "watch", "shoes", "dupatta", "shawl"):
            if any(self._contains_phrase(text, alias) for alias in self.CATEGORY_ALIASES[key]):
                requested.append(key)
        return tuple(dict.fromkeys(requested))

    def _has_any_accessory_question_word(self, text: str) -> bool:
        return any(
            self._contains_phrase(text, alias)
            for key in ("accessories", "bag", "jewelry", "shoes", "watch", "perfume")
            for alias in self.CATEGORY_ALIASES[key]
        )

    @staticmethod
    def _accessory_match_label(category_key: str) -> str:
        return {
            "bag": "bag",
            "jewelry": "jewelry",
            "shoes": "shoe",
        }.get(category_key, category_key.replace("_", " "))

    def _canonical_category_key(self, value: str | None) -> str | None:
        text = normalize_fashion_text(value)
        if not text:
            return None
        for key, aliases in self.CATEGORY_ALIASES.items():
            if text == key or any(text == normalize_fashion_text(alias) for alias in aliases):
                return key
        if text in {"accessory", "accessories"}:
            return "accessories"
        return None

    def _extract_gender(self, text: str) -> str | None:
        for gender, aliases in self.GENDER_ALIASES.items():
            if any(self._contains_phrase(text, alias) for alias in aliases):
                return gender
        return None

    def _extract_color(self, text: str) -> tuple[str | None, str | None]:
        candidates = sorted(self.COLOR_ALIASES.values(), key=lambda item: max(len(alias) for alias in item[2]), reverse=True)
        for canonical, family, aliases in candidates:
            if any(self._contains_phrase(text, alias) for alias in aliases):
                return canonical, family
        return None, None

    def _extract_size(self, *, text: str, category_key: str | None) -> str | None:
        for pattern in (self.SIZE_PATTERN, self.REVERSE_SIZE_PATTERN):
            match = pattern.search(text)
            if match:
                return self._normalize_size(match.group(1))
        if category_key in {"blouse", "panjabi", "salwar_kameez", "shoes", "shirt", "pant", "watch", "perfume", "jewelry"}:
            bare = self.BARE_SIZE_PATTERN.search(text)
            if bare and not self._contains_phrase(text, "under"):
                return self._normalize_size(bare.group(1))
        return None

    def _normalize_size(self, value: str) -> str:
        normalized = normalize_fashion_text(value)
        return normalized.upper() if normalized.isalpha() else normalized

    def _extract_budget(self, question: str) -> tuple[float | None, float | None]:
        budget_min: float | None = None
        budget_max: float | None = None
        max_match = self.MAX_PRICE_PATTERN.search(question)
        if max_match:
            value = max_match.group(1) or max_match.group(2)
            if value:
                budget_max = float(value)
        min_match = self.MIN_PRICE_PATTERN.search(question)
        if min_match:
            budget_min = float(min_match.group(1))
        return budget_min, budget_max

    def _extract_alias(self, text: str, aliases_by_label: dict[str, tuple[str, ...]]) -> str | None:
        for label, aliases in aliases_by_label.items():
            if any(self._contains_phrase(text, alias) for alias in aliases):
                return label
        return None

    def _resolve_design_id(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        focused_product_ids: tuple[str, ...],
        last_primary_product_id: str | None,
    ) -> str | None:
        id_candidates = [*focused_product_ids]
        if last_primary_product_id:
            id_candidates.append(last_primary_product_id)
        for product_id in id_candidates:
            for item in items:
                if item.product_id == product_id and self._item_design_id(item):
                    return self._item_design_id(item)

        text = normalize_fashion_text(question)
        for item in items:
            design_id = self._item_design_id(item)
            if design_id and self._contains_phrase(text, normalize_fashion_text(design_id)):
                return design_id
            if self._contains_phrase(text, normalize_fashion_text(item.sku)):
                return design_id

        grouped: dict[str, list[InventoryItemRecord]] = defaultdict(list)
        for item in items:
            design_id = self._item_design_id(item)
            if design_id:
                grouped[design_id].append(item)
        best_design_id: str | None = None
        best_score = 0.0
        for design_id, group_items in grouped.items():
            group_text = " ".join(self._item_text(item) for item in group_items)
            score = self._lexical_overlap_score(question, group_text)
            variant_group_name = normalize_fashion_text(group_items[0].metadata.get("variant_group_name"))
            if variant_group_name and self._contains_phrase(text, variant_group_name):
                score += 5.0
            if score > best_score:
                best_score = score
                best_design_id = design_id
        if best_score >= 1.5:
            return best_design_id
        return None

    def _resolve_anchor_item(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
    ) -> InventoryItemRecord | None:
        if slots.design_id:
            variants = self._same_design_items(items, slots.design_id)
            if variants:
                if slots.color_family:
                    color_matches = [item for item in variants if self._item_color_matches(item, slots.color_family, slots.color)]
                    if color_matches:
                        return sorted(color_matches, key=lambda item: (-item.stock, self._item_price_value(item)))[0]
                return sorted(variants, key=lambda item: (-item.stock, self._item_price_value(item)))[0]
        ranked = self._rank_search_items(question=question, items=[item for item in items if not self._is_accessory_item(item)], slots=slots, top_k=1)
        return ranked[0].item if ranked else None

    def _same_design_items(self, items: list[InventoryItemRecord], design_id: str) -> list[InventoryItemRecord]:
        return [item for item in items if self._item_design_id(item) == design_id]

    def _same_design_or_category_alternatives(
        self,
        base: InventoryItemRecord,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
    ) -> list[InventoryItemRecord]:
        design_id = self._item_design_id(base)
        base_color_family = self._item_color_family(base)
        alternatives = [
            item
            for item in items
            if item.product_id != base.product_id
            and item.stock > 0
            and ((design_id and self._item_design_id(item) == design_id) or self._item_category_matches(item, slots.category_key or ""))
        ]
        return sorted(
            alternatives,
            key=lambda item: (
                0 if design_id and self._item_design_id(item) == design_id else 1,
                0 if base_color_family and self._item_color_matches(item, base_color_family, None) else 1,
                -item.stock,
                self._item_price_value(item),
                item.name.casefold(),
            ),
        )

    def _item_category_matches(self, item: InventoryItemRecord, category_key: str | None) -> bool:
        if not category_key:
            return True
        item_text = self._item_text(item)
        identity_text = normalize_fashion_text(
            " ".join(
                [
                    item.name,
                    item.category or "",
                    " ".join(item.tags),
                    str(item.attributes.get("category", "")),
                    str(item.attributes.get("category_key", "")),
                    str(item.attributes.get("product_type", "")),
                ]
            )
        )
        item_category_key = self._canonical_category_key(item.attributes.get("category_key")) or self._canonical_category_key(item.category)
        if item_category_key == category_key:
            return True
        if category_key in {"accessories", "jewelry", "bag", "perfume", "watch", "shoes"}:
            return self._is_accessory_item(item) and (
                category_key == "accessories" or any(self._contains_phrase(item_text, alias) for alias in self.CATEGORY_ALIASES[category_key])
            )
        return any(self._contains_phrase(identity_text, alias) for alias in self.CATEGORY_ALIASES.get(category_key, ()))

    @staticmethod
    def _is_accessory_category(category_key: str) -> bool:
        return category_key in {"accessories", "jewelry", "bag", "perfume", "watch", "shoes", "dupatta", "shawl"}

    def _is_accessory_item(self, item: InventoryItemRecord) -> bool:
        item_text = self._item_text(item)
        category_key = self._canonical_category_key(item.attributes.get("category_key")) or self._canonical_category_key(item.category)
        if category_key in {"saree", "blouse", "panjabi", "kurti", "salwar_kameez", "shirt", "pant", "cosmetics", "beauty"}:
            return False
        if category_key in {"bag", "jewelry", "accessories", "perfume", "watch", "shoes"}:
            return True
        if item.attributes.get("accessory_type") or item.attributes.get("compatible_design_ids"):
            return True
        return any(
            self._contains_phrase(item_text, alias)
            for key in ("bag", "jewelry", "accessories", "perfume", "watch", "shoes")
            for alias in self.CATEGORY_ALIASES[key]
        )

    def _item_gender_matches(self, item: InventoryItemRecord, requested_gender: str | None) -> bool:
        if not requested_gender:
            return True
        values = [
            item.attributes.get("gender"),
            item.attributes.get("section"),
            item.metadata.get("gender"),
            item.metadata.get("section"),
            item.name,
            " ".join(item.tags),
        ]
        normalized_values = " ".join(normalize_fashion_text(value) for value in values if value)
        if requested_gender == "men":
            if any(self._contains_phrase(normalized_values, marker) for marker in ("men", "mens", "men s", "male", "gents", "unisex")):
                return True
            return False
        if requested_gender == "women":
            if any(self._contains_phrase(normalized_values, marker) for marker in ("women", "womens", "women s", "female", "ladies", "lady", "unisex")):
                return True
            return False
        if requested_gender == "unisex":
            return self._contains_phrase(normalized_values, "unisex")
        return True

    def _item_color_matches(self, item: InventoryItemRecord, color_family: str | None, color: str | None) -> bool:
        if not color_family and not color:
            return True
        values = [
            item.attributes.get("color"),
            item.attributes.get("color_family"),
            item.metadata.get("color"),
            item.metadata.get("color_family"),
            item.name,
            " ".join(item.tags),
        ]
        return any(self._color_value_matches(value, color_family, color) for value in values)

    def _color_value_matches(self, value: object | None, color_family: str | None, color: str | None) -> bool:
        text = normalize_fashion_text(value)
        if not text:
            return False
        if color and self._contains_phrase(text, color):
            return True
        if color_family and self._contains_phrase(text, color_family):
            return True
        if color_family:
            for canonical, family, aliases in self.COLOR_ALIASES.values():
                if family == color_family and any(self._contains_phrase(text, alias) for alias in aliases + (canonical,)):
                    return True
        return False

    def _item_color_family(self, item: InventoryItemRecord) -> str | None:
        explicit = normalize_fashion_text(item.attributes.get("color_family") or item.metadata.get("color_family"))
        if explicit:
            return explicit
        color_text = normalize_fashion_text(item.attributes.get("color") or item.name)
        for canonical, family, aliases in self.COLOR_ALIASES.values():
            if any(self._contains_phrase(color_text, alias) for alias in aliases + (canonical,)):
                return family
        return None

    def _item_size_matches(self, item: InventoryItemRecord, size: str) -> bool:
        requested = self._normalize_size(size)
        values = [
            item.attributes.get("size"),
            item.attributes.get("available_sizes"),
            item.metadata.get("size"),
            item.name,
            " ".join(item.tags),
        ]
        for value in values:
            parts = self._split_multi_value(value)
            if requested in {self._normalize_size(part) for part in parts}:
                return True
        return False

    def _item_style_matches(self, item: InventoryItemRecord, style: str) -> bool:
        item_text = self._item_text(item)
        aliases = self.STYLE_ITEM_ALIASES.get(style, (style,))
        return any(self._contains_phrase(item_text, alias) for alias in aliases)

    def _item_design_id(self, item: InventoryItemRecord) -> str | None:
        value = item.attributes.get("design_id") or item.metadata.get("design_id")
        return str(value).strip() if value else None

    def _item_text(self, item: InventoryItemRecord) -> str:
        pieces: list[str] = [
            item.product_id,
            item.sku,
            item.name,
            item.category or "",
            item.brand or "",
            item.short_description or "",
            item.full_description or "",
            " ".join(item.tags),
        ]
        pieces.extend(f"{key} {value}" for key, value in sorted(item.attributes.items()))
        pieces.extend(f"{key} {value}" for key, value in sorted(item.metadata.items()) if not isinstance(value, (dict, list)))
        for value in item.metadata.values():
            if isinstance(value, list):
                pieces.extend(str(part) for part in value)
        return normalize_fashion_text(" ".join(pieces))

    def _lexical_overlap_score(self, question: str, candidate_text: str) -> float:
        query_terms = self._query_terms(question)
        if not query_terms:
            return 0.0
        score = 0.0
        for term in query_terms:
            if self._contains_phrase(candidate_text, term):
                score += 1.0 if len(term) <= 4 else 1.25
        return score

    def _query_terms(self, question: str) -> list[str]:
        text = normalize_fashion_text(question)
        raw_terms = [term for term in re.split(r"\s+", text) if len(term) > 1]
        excluded = set(self.STOPWORDS)
        for aliases in self.CATEGORY_ALIASES.values():
            excluded.update(alias for alias in aliases if " " not in alias)
        terms: list[str] = []
        seen: set[str] = set()
        for term in raw_terms:
            if term in excluded:
                continue
            if term.isdigit() and len(term) > 2:
                continue
            if term not in seen:
                seen.add(term)
                terms.append(term)
        return terms

    def _has_tech_context_without_fashion_context(self, text: str) -> bool:
        has_tech = any(self._contains_phrase(text, term) for term in self.TECH_CONTEXT_TERMS)
        has_strong_fashion = any(
            self._contains_phrase(text, term)
            for term in (
                "saree",
                "sari",
                "blouse",
                "panjabi",
                "jewelry",
                "necklace",
                "bangle",
                "bridal",
                "wedding",
                "katan",
                "jamdani",
            )
        )
        return has_tech and not has_strong_fashion

    def _available_size_list(self, items: list[InventoryItemRecord]) -> str:
        sizes: list[str] = []
        seen: set[str] = set()
        for item in items:
            for value in (item.attributes.get("size"), item.attributes.get("available_sizes")):
                for part in self._split_multi_value(value):
                    size = self._normalize_size(part)
                    if size and size not in seen and item.stock > 0:
                        seen.add(size)
                        sizes.append(size)
        return self._natural_join(sizes[:6])

    def _color_stock_list(self, items: list[InventoryItemRecord], *, include_stock: bool = True) -> str:
        values: list[str] = []
        seen: set[str] = set()
        for item in sorted(items, key=lambda value: (self._item_color_sort_text(value), value.name.casefold())):
            color = item.attributes.get("color") or self._item_color_sort_text(item)
            color_text = str(color)
            if color_text.casefold() in seen:
                continue
            seen.add(color_text.casefold())
            values.append(f"{color_text} ({item.stock} in stock)" if include_stock else color_text)
        return self._natural_join(values)

    def _item_color_sort_text(self, item: InventoryItemRecord) -> str:
        return normalize_fashion_text(item.attributes.get("color") or item.name)

    def _format_option(self, item: InventoryItemRecord) -> str:
        return f"{item.name} ({self._format_price(item)}, {item.stock} in stock)"

    def _format_price(self, item: InventoryItemRecord) -> str:
        if item.price is None:
            return item.currency
        amount = f"{item.price:,.0f}" if float(item.price).is_integer() else f"{item.price:,.2f}"
        return f"{item.currency} {amount}"

    def _item_price_value(self, item: InventoryItemRecord) -> float:
        return item.price if item.price is not None else float("inf")

    def _split_multi_value(self, value: object | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            parts = [str(part) for part in value]
        else:
            parts = re.split(r"[,/;|]+", str(value))
        normalized = [part.strip() for part in parts if part and part.strip()]
        return normalized

    def _outcome(
        self,
        *,
        answer: str,
        intent: str,
        product_ids: tuple[str, ...] = (),
        cross_sell_product_ids: tuple[str, ...] = (),
        total_matches: int = 0,
        confidence: float,
        slots: FashionRetailSlots,
        follow_up_question: str | None = None,
        abstained: bool = False,
        abstention_reason: str | None = None,
        reasoning_steps: tuple[str, ...] = (),
    ) -> FashionRetailOutcome:
        answer = self._localize_answer(answer=answer, slots=slots)
        return FashionRetailOutcome(
            answer=answer,
            intent=intent,
            product_ids=product_ids,
            cross_sell_product_ids=cross_sell_product_ids,
            total_matches=total_matches,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            slots=slots,
            follow_up_question=follow_up_question,
            abstained=abstained,
            abstention_reason=abstention_reason,
            reasoning_steps=reasoning_steps,
        )

    def _detect_language(self, question: str) -> str:
        if BANGLA_TEXT_PATTERN.search(question):
            return "bangla"
        text = normalize_fashion_text(question)
        banglish_markers = (
            "ache",
            "ase",
            "nai",
            "pawa",
            "jabe",
            "lagbe",
            "dekh",
            "dekhan",
            "jonno",
            "sathe",
            "shathe",
            "manabe",
            "ekoi",
            "onno",
            "kom",
            "dam",
        )
        if any(self._contains_phrase(text, marker) for marker in banglish_markers):
            return "banglish"
        return "english"

    def _localize_answer(self, *, answer: str, slots: FashionRetailSlots) -> str:
        if slots.language == "bangla":
            localized = answer
            localized = localized.replace(" is available in size ", " সাইজ ")
            replacements = (
                ("Yes.", "জি,"),
                ("Yes,", "জি,"),
                ("I could not find an exact in-catalog", "আমি ক্যাটালগে ঠিক এমন"),
                ("I don't have an exact", "ঠিক"),
                ("; closest available options are:", " পাচ্ছি না। কাছাকাছি অপশনগুলো হলো:"),
                ("for those details yet", "এখনও পাচ্ছি না"),
                ("I have a few good options:", "কয়েকটা ভালো অপশন আছে:"),
                ("My first pick would be", "আমার প্রথম পছন্দ হবে"),
                ("I found", "আমি পেয়েছি"),
                ("I do not see", "আমি ক্যাটালগে পাচ্ছি না"),
                ("these are the closest available options", "নিকটতম স্টকে থাকা অপশনগুলো হলো"),
                ("We have", "আমাদের কাছে আছে"),
                ("is available", "স্টকে আছে"),
                ("available:", "স্টকে আছে:"),
                ("currently out of stock", "এখন স্টকে নেই"),
                ("out of stock", "স্টকে নেই"),
                ("in stock", "স্টকে আছে"),
                ("Other in-stock colors in the same design", "একই ডিজাইনে অন্য স্টকে থাকা রঙ"),
                ("In-stock colors in the same design", "একই ডিজাইনে স্টকে থাকা রঙ"),
                ("Closest available option", "নিকটতম স্টকে থাকা অপশন"),
                ("Good bag matches", "ভালো ব্যাগ ম্যাচিং অপশন"),
                ("Good jewelry matches", "ভালো গয়না ম্যাচিং অপশন"),
                ("Good shoe matches", "ভালো জুতা ম্যাচিং অপশন"),
                ("Good matches", "ভালো ম্যাচিং অপশন"),
                ("matching option(s)", "ম্যাচিং অপশন"),
            )
            for source, target in replacements:
                localized = localized.replace(source, target)
            localized = localized.replace(" in that same design, but it is ", " একই ডিজাইনে, কিন্তু এটি ")
            localized = localized.replace(" in size ", " সাইজ ")
            localized = localized.replace(" for ", " এর জন্য ")
            localized = localized.replace(", and ", ", এবং ")
            localized = localized.replace(" and ", " এবং ")
            localized = re.sub(r"(Size\s+([a-z0-9.]+))\s+সাইজ\s+\2:", r"\1:", localized, flags=re.IGNORECASE)
            localized = re.sub(r"(?<=, )(\d+)\s+স্টকে আছে", r"\1টি স্টকে আছে", localized)
            localized = re.sub(r"(?<=\()(\d+)\s+স্টকে আছে", r"\1টি স্টকে আছে", localized)
            localized = re.sub(r"\b(\d+)\s+ম্যাচিং অপশন", r"\1টি ম্যাচিং অপশন", localized)
            localized = re.sub(r"ভালো ([^:]+) ম্যাচিং অপশন এর জন্য ([^:]+):", r"\2 এর জন্য ভালো \1 ম্যাচিং অপশন:", localized)
            localized = re.sub(r"ভালো ম্যাচিং অপশন এর জন্য ([^:]+):", r"\1 এর জন্য ভালো ম্যাচিং অপশন:", localized)
            return localized
        if slots.language == "banglish":
            localized = answer
            localized = localized.replace(" is available in size ", " size ")
            replacements = (
                ("Yes.", "Ji,"),
                ("Yes,", "Ji,"),
                ("I could not find an exact in-catalog", "Catalog e exact"),
                ("I don't have an exact", "Exact"),
                ("; closest available options are:", " catalog e pacchi na. Closest option gulo:"),
                ("for those details yet", "ekhon pacchi na"),
                ("I have a few good options:", "Kichu bhalo option ache:"),
                ("My first pick would be", "Amar first pick hobe"),
                ("I found", "Ami peyechi"),
                ("I do not see", "Ami catalog e pacchi na"),
                ("these are the closest available options", "closest available option gulo"),
                ("We have", "Amader kache ache"),
                ("is available", "available ache"),
                ("available:", "available ache:"),
                ("currently out of stock", "ekhon stock e nei"),
                ("out of stock", "stock e nei"),
                ("in stock", "stock e ache"),
                ("Other in-stock colors in the same design", "Same design e onno stock e thaka color"),
                ("In-stock colors in the same design", "Same design e stock e thaka color"),
                ("Closest available option", "Closest available option"),
                ("Good matches", "Bhalo matching option"),
            )
            for source, target in replacements:
                localized = localized.replace(source, target)
            localized = localized.replace(" in that same design, but it is ", " same design e, kintu eta ")
            localized = localized.replace(" in size ", " size ")
            localized = localized.replace(" for ", " er jonno ")
            localized = re.sub(r"(Size\s+([a-z0-9.]+))\s+size\s+\2:", r"\1:", localized, flags=re.IGNORECASE)
            localized = re.sub(
                r"^Exact under BDT ([\d,]+) ([^.]+?) catalog e pacchi na\.",
                r"BDT \1 er moddhe exact \2 catalog e pacchi na.",
                localized,
            )
            return localized
        return answer

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        normalized_phrase = normalize_fashion_text(phrase)
        if not text or not normalized_phrase:
            return False
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])", text) is not None

    @staticmethod
    def _natural_join(values: list[str] | tuple[str, ...]) -> str:
        cleaned = [value for value in values if value]
        if not cleaned:
            return ""
        if len(cleaned) == 1:
            return cleaned[0]
        if len(cleaned) == 2:
            return f"{cleaned[0]} and {cleaned[1]}"
        return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"

    # -------------------------------------------------------------------------
    # Styling advice engine (rules-based from product metadata)
    # -------------------------------------------------------------------------

    _COLOR_PAIRING_RULES: dict[str, list[str]] = {
        "red": ["gold", "black", "white", "silver", "nude"],
        "maroon": ["gold", "antique gold", "cream", "black", "beige"],
        "navy": ["gold", "silver", "white", "cream", "rose gold"],
        "navy blue": ["gold", "silver", "white", "cream", "rose gold"],
        "blue": ["gold", "silver", "white"],
        "royal blue": ["gold", "silver", "white"],
        "green": ["gold", "antique gold", "cream", "white"],
        "bottle green": ["gold", "antique gold", "cream", "rose gold"],
        "black": ["gold", "silver", "white", "red"],
        "white": ["gold", "silver", "blue", "red", "pink"],
        "yellow": ["white", "black", "green"],
        "pink": ["gold", "silver", "white", "rose gold"],
        "purple": ["gold", "silver", "white"],
        "orange": ["gold", "cream", "white"],
        "mustard": ["black", "maroon", "green"],
    }

    _OCCASION_WEIGHT: dict[str, list[str]] = {
        "wedding": ["heavy", "zari", "meena", "katan", "silk", "bridal", "embroidered"],
        "party": ["embroidered", "printed", "buti", "floral", "silk"],
        "office": ["plain", "cotton", "simple", "lightweight", "formal"],
        "casual": ["cotton", "linen", "plain", "lightweight"],
        "eid": ["heavy", "zari", "meena", "katan", "embroidered", "buti"],
        "puja": ["cotton", "silk", "linen", "traditional"],
        "daily wear": ["cotton", "plain", "lightweight"],
    }

    def _answer_styling_advice(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> FashionRetailOutcome | None:
        color = slots.color or slots.color_family
        occasion = slots.occasion
        budget_max = slots.budget_max

        complementary_colors = self._COLOR_PAIRING_RULES.get(
            (color or "").casefold(), ["gold", "silver", "white"]
        ) if color else ["gold", "silver", "white", "black"]

        accessory_keys = ("bag", "jewelry", "shoes", "dupatta", "shawl", "watch")
        suggestions: list[InventoryItemRecord] = []

        for key in accessory_keys:
            matches = [
                item
                for item in items
                if self._item_category_matches(item, key)
                and item.stock > 0
                and (budget_max is None or (item.price or 0) <= budget_max)
                and any(
                    (item.attributes.get("color_family") or "").casefold() == cc
                    or (item.attributes.get("color") or "").casefold() == cc
                    for cc in complementary_colors
                )
            ]
            if not matches:
                matches = [
                    item
                    for item in items
                    if self._item_category_matches(item, key) and item.stock > 0
                    and (budget_max is None or (item.price or 0) <= budget_max)
                ]
            if matches:
                matches.sort(key=lambda x: -x.stock)
                suggestions.append(matches[0])

        if not suggestions:
            return None

        color_label = color or "your saree"
        occasion_label = f" for {occasion}" if occasion else ""
        complement_str = ", ".join(complementary_colors[:3])
        lines: list[str] = [
            f"{color_label.title()} color pairs well with {complement_str} tones{occasion_label}.\n"
        ]
        for item in suggestions[:top_k]:
            lines.append(f"- **{item.name}** — BDT {(item.price or 0):,.0f}, Stock: {item.stock}")
            item_color = item.attributes.get("color") or item.attributes.get("color_family") or ""
            item_occasion = item.attributes.get("occasion") or ""
            if item_color:
                lines.append(f"  Color: {item_color}")
            if item_occasion and occasion and occasion.casefold() in item_occasion.casefold():
                lines.append(f"  Great for: {occasion}")

        if occasion in self._OCCASION_WEIGHT:
            weight_hints = self._OCCASION_WEIGHT[occasion]
            lines.append(
                f"\nFor {occasion}, prefer {', '.join(weight_hints[:3])} fabric/work for the best look."
            )

        return self._outcome(
            answer="\n".join(lines),
            intent="fashion_styling_advice",
            product_ids=tuple(item.product_id for item in suggestions[:top_k]),
            total_matches=len(suggestions),
            confidence=0.82,
            slots=slots,
            reasoning_steps=(
                f"Applied color pairing rules for {color_label}.",
                f"Filtered accessories by complementary colors: {complement_str}.",
                "Only returned in-stock items within budget.",
            ),
        )

    # -------------------------------------------------------------------------
    # Multi-brand ambiguity clarification
    # -------------------------------------------------------------------------

    def _answer_multi_brand_clarification(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> FashionRetailOutcome | None:
        brand = self._detect_brand(normalize_fashion_text(question))
        if not brand or not slots.category_key:
            return None

        brand_items = [
            item
            for item in items
            if self._item_category_matches(item, slots.category_key)
            and (item.brand or "").casefold() == brand.casefold()
        ]
        if not brand_items:
            return None

        fabrics_available = sorted({
            (item.attributes.get("fabric") or "").title()
            for item in brand_items
            if item.attributes.get("fabric")
        })

        if len(fabrics_available) > 1:
            fabric_list = ", ".join(fabrics_available)
            return self._outcome(
                answer=(
                    f"I found multiple {brand} {slots.category_label or slots.category_key}s. "
                    f"Available fabric types: {fabric_list}. "
                    f"Which fabric do you prefer?"
                ),
                intent="fashion_multi_brand_clarification",
                product_ids=tuple(item.product_id for item in brand_items[:top_k]),
                total_matches=len(brand_items),
                confidence=0.75,
                slots=slots,
                follow_up_question=f"Which {brand} {slots.category_key} fabric do you prefer? {fabric_list}?",
                reasoning_steps=(f"Found {len(brand_items)} {brand} products with multiple fabric options.",),
            )
        return None

    def _detect_brand(self, text: str) -> str | None:
        for brand, aliases in self.BRAND_ALIASES.items():
            if any(self._contains_phrase(text, alias) for alias in aliases):
                return brand.title()
        return None

    def _answer_fashion_compare(
        self,
        *,
        question: str,
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> FashionRetailOutcome | None:
        """Compare two products/types side-by-side on price, fabric, occasion, durability, stock."""
        text = normalize_fashion_text(question)

        # Find two distinct sides to compare
        side_keys: list[str] = []
        for key, aliases in self.CATEGORY_ALIASES.items():
            if any(self._contains_phrase(text, alias) for alias in aliases):
                if key not in side_keys:
                    side_keys.append(key)
            if len(side_keys) == 2:
                break

        # Fallback: fabric comparison
        if len(side_keys) < 2:
            fabric_sides: list[str] = []
            for key, aliases in self.FABRIC_ALIASES.items():
                if any(self._contains_phrase(text, alias) for alias in aliases):
                    if key not in fabric_sides:
                        fabric_sides.append(key)
                if len(fabric_sides) == 2:
                    break
            if len(fabric_sides) == 2:
                return self._compare_by_fabric(fabric_sides, items, slots, top_k)

        if len(side_keys) < 2:
            return None

        a_key, b_key = side_keys[0], side_keys[1]

        def _eligible(item: InventoryItemRecord, category_key: str) -> bool:
            if item.stock <= 0:
                return False
            if not self._item_category_matches(item, category_key):
                return False
            if slots.gender and not self._item_gender_matches(item, slots.gender):
                return False
            if slots.budget_min is not None and (item.price is None or item.price < slots.budget_min):
                return False
            if slots.budget_max is not None and (item.price is None or item.price > slots.budget_max):
                return False
            if slots.occasion and not self._contains_phrase(self._item_text(item), slots.occasion):
                return False
            return True

        a_items = [i for i in items if _eligible(i, a_key)]
        b_items = [i for i in items if _eligible(i, b_key)]

        if not a_items and not b_items:
            return None

        def _best(lst: list[InventoryItemRecord]) -> InventoryItemRecord | None:
            return sorted(lst, key=lambda i: (-i.stock, self._item_price_value(i)))[0] if lst else None

        a_best = _best(a_items)
        b_best = _best(b_items)

        a_label = self.CATEGORY_LABELS.get(a_key, a_key)
        b_label = self.CATEGORY_LABELS.get(b_key, b_key)

        lines: list[str] = [f"**{a_label} vs {b_label}:**\n"]

        def _row(label: str, a_val: str, b_val: str) -> str:
            return f"| {label} | {a_val} | {b_val} |"

        lines.append(f"| | {a_label} | {b_label} |")
        lines.append("|---|---|---|")

        if a_best and b_best:
            lines.append(_row("Best match", a_best.name[:40], b_best.name[:40]))
            lines.append(_row("Price", self._format_price(a_best), self._format_price(b_best)))
            lines.append(_row("Stock", str(a_best.stock), str(b_best.stock)))
            a_fabric = a_best.attributes.get("fabric", "—")
            b_fabric = b_best.attributes.get("fabric", "—")
            lines.append(_row("Fabric", a_fabric, b_fabric))
            a_occ = a_best.attributes.get("occasion") or (a_best.tags[0] if a_best.tags else "—")
            b_occ = b_best.attributes.get("occasion") or (b_best.tags[0] if b_best.tags else "—")
            lines.append(_row("Occasion", a_occ, b_occ))
            lines.append(_row("In-stock count", str(len(a_items)), str(len(b_items))))
        elif a_best:
            lines.append(f"{a_label} is available but we currently have no {b_label} in stock.")
        else:
            lines.append(f"{b_label} is available but we currently have no {a_label} in stock.")

        # Recommendation
        if a_best and b_best:
            a_price = self._item_price_value(a_best)
            b_price = self._item_price_value(b_best)
            if a_price < b_price:
                lines.append(f"\n💡 {a_label} is the budget-friendly option. {b_label} is the premium pick.")
            elif b_price < a_price:
                lines.append(f"\n💡 {b_label} is the budget-friendly option. {a_label} is the premium pick.")
            else:
                lines.append(f"\n💡 Both are similarly priced — choose by fabric and occasion.")

        all_pids = tuple(([a_best.product_id] if a_best else []) + ([b_best.product_id] if b_best else []))
        return self._outcome(
            answer="\n".join(lines),
            intent="fashion_compare",
            product_ids=all_pids,
            total_matches=len(a_items) + len(b_items),
            confidence=0.80,
            slots=slots,
            reasoning_steps=(f"Compared {a_label} vs {b_label} on price, fabric, occasion, stock.",),
        )

    def _compare_by_fabric(
        self,
        fabric_sides: list[str],
        items: list[InventoryItemRecord],
        slots: FashionRetailSlots,
        top_k: int,
    ) -> FashionRetailOutcome | None:
        a_fab, b_fab = fabric_sides[0], fabric_sides[1]
        a_items = [i for i in items if i.attributes.get("fabric") == a_fab and i.stock > 0]
        b_items = [i for i in items if i.attributes.get("fabric") == b_fab and i.stock > 0]
        if not a_items and not b_items:
            return None

        def _best(lst: list[InventoryItemRecord]) -> InventoryItemRecord | None:
            return sorted(lst, key=lambda i: (-i.stock, self._item_price_value(i)))[0] if lst else None

        a_best = _best(a_items)
        b_best = _best(b_items)
        lines = [f"**{a_fab.title()} vs {b_fab.title()} fabric:**\n"]
        lines.append(f"| | {a_fab.title()} | {b_fab.title()} |")
        lines.append("|---|---|---|")
        if a_best and b_best:
            lines.append(f"| Example | {a_best.name[:35]} | {b_best.name[:35]} |")
            lines.append(f"| Price | {self._format_price(a_best)} | {self._format_price(b_best)} |")
            lines.append(f"| In-stock products | {len(a_items)} | {len(b_items)} |")
        all_pids = tuple(
            ([a_best.product_id] if a_best else []) + ([b_best.product_id] if b_best else [])
        )
        return self._outcome(
            answer="\n".join(lines),
            intent="fashion_compare",
            product_ids=all_pids,
            total_matches=len(a_items) + len(b_items),
            confidence=0.75,
            slots=slots,
            reasoning_steps=(f"Compared {a_fab} vs {b_fab} fabric options.",),
        )
