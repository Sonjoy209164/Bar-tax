from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryAskRequest, InventorySearchFilters
from app.inventory.conversation_context import hydrate_request_from_state
from app.inventory.conversation_state import ConversationStateStore
from app.inventory.memory import InventoryMemoryResolver
from app.inventory.memory_policy import product_focus_expired, should_use_product_focus, to_iso
from app.inventory.ontology import ProductOntology


@dataclass(frozen=True)
class MemoryTurnCase:
    case_id: str
    scenario_id: str
    turn: int
    user: str
    description: str
    expected_policy: str  # allow|block|expired|none
    expected_resolved_ids: list[str]
    expected_focus_after: list[str] | None
    expected_category_after: str | None
    response_intent: str
    response_slots: dict[str, Any]
    response_product_ids: list[str]
    response_primary_product_id: str | None
    response_confidence: float
    response_abstained: bool = False
    memory_source: str | None = None
    age_focus_minutes_before: int | None = None


@dataclass
class MemoryEvalResult:
    case_id: str
    scenario_id: str
    turn: int
    user: str
    passed: bool
    failures: list[str]
    expected_policy: str
    actual_policy_allowed: bool
    actual_policy_expired: bool
    policy_reason: str
    hydrated_used_state: bool
    hydration_reason: str | None
    resolved_ids: list[str]
    used_memory: bool
    ignored_memory_reason: str | None
    focus_after: list[str]
    category_after: str | None


def build_cases() -> list[MemoryTurnCase]:
    cases: list[MemoryTurnCase] = []

    def add(
        scenario: str,
        user: str,
        description: str,
        expected_policy: str,
        expected_resolved_ids: list[str] | None,
        expected_focus_after: list[str] | None,
        expected_category_after: str | None,
        intent: str,
        slots: dict[str, Any] | None = None,
        products: list[str] | None = None,
        primary: str | None = None,
        confidence: float = 0.9,
        abstained: bool = False,
        memory_source: str | None = None,
        age_focus_minutes_before: int | None = None,
    ) -> None:
        turn = sum(1 for case in cases if case.scenario_id == scenario) + 1
        cases.append(
            MemoryTurnCase(
                case_id=f"{scenario}_{turn:02d}",
                scenario_id=scenario,
                turn=turn,
                user=user,
                description=description,
                expected_policy=expected_policy,
                expected_resolved_ids=list(expected_resolved_ids or []),
                expected_focus_after=expected_focus_after,
                expected_category_after=expected_category_after,
                response_intent=intent,
                response_slots=dict(slots or {}),
                response_product_ids=list(products or []),
                response_primary_product_id=primary,
                response_confidence=confidence,
                response_abstained=abstained,
                memory_source=memory_source,
                age_focus_minutes_before=age_focus_minutes_before,
            )
        )

    # 1. Basic Banglish product memory.
    s = "S01_basic_panjabi"
    add(s, "black panjabi under 3000 dekhao", "new product search writes focus", "block", [], ["panjabi_1", "panjabi_2", "panjabi_3"], "panjabi", "fashion_search", {"category_key": "panjabi", "color_family": "black", "budget_max": 3000}, ["panjabi_1", "panjabi_2", "panjabi_3"], "panjabi_1")
    add(s, "etar price koto?", "direct Banglish pronoun resolves primary", "allow", ["panjabi_1"], ["panjabi_1", "panjabi_2", "panjabi_3"], "panjabi", "fashion_price", {}, [], None)
    add(s, "second one er size ache?", "ordinal resolves second result", "allow", ["panjabi_2"], ["panjabi_1", "panjabi_2", "panjabi_3"], "panjabi", "fashion_size_availability", {}, [], None)
    add(s, "M size ache?", "short size follow-up resolves primary", "allow", ["panjabi_1"], ["panjabi_1", "panjabi_2", "panjabi_3"], "panjabi", "fashion_size_availability", {}, [], None)
    add(s, "same design blue color e ache?", "same-design variant query uses previous focus", "allow", ["panjabi_1"], ["panjabi_blue_1"], "panjabi", "fashion_search", {"category_key": "panjabi", "color_family": "blue", "variant_group_id": "panjabi-vg-1"}, ["panjabi_blue_1"], "panjabi_blue_1")
    add(s, "red saree dekhao", "new explicit category overrides panjabi", "block", [], ["saree_1", "saree_2"], "saree", "fashion_search", {"category_key": "saree", "color_family": "red"}, ["saree_1", "saree_2"], "saree_1")
    add(s, "etar stock ache?", "follow-up now points to saree", "allow", ["saree_1"], ["saree_1", "saree_2"], "saree", "fashion_stock", {}, [], None)
    add(s, "third one ache?", "third unavailable when only two shown should not invent ID", "allow", [], ["saree_1", "saree_2"], "saree", "fashion_stock", {}, [], None)
    add(s, "first one ta cart e add korte chai", "order follow-up resolves first saree", "allow", ["saree_1"], ["saree_1", "saree_2"], "saree", "cart_add", {}, [], None)
    add(s, "white sandal ache?", "new sandal search must ignore saree focus", "block", [], ["sandal_1"], "sandal", "fashion_search", {"category_key": "sandal", "color_family": "white"}, ["sandal_1"], "sandal_1")

    # 2. Boundary detours must not overwrite product focus.
    s = "S02_boundary_detours"
    add(s, "red saree dekhao", "new saree focus", "block", [], ["saree_red_1", "saree_red_2"], "saree", "fashion_search", {"category_key": "saree", "color_family": "red"}, ["saree_red_1", "saree_red_2"], "saree_red_1")
    add(s, "amar ekta gf lagbe", "romantic off-topic must not write shopping focus", "block", [], ["saree_red_1", "saree_red_2"], "saree", "romantic_off_topic", {"risk_level": "low", "recommended_categories": ["gift", "perfume"]}, [], None, 0.82)
    add(s, "etar price koto?", "saree focus survives romantic detour", "allow", ["saree_red_1"], ["saree_red_1", "saree_red_2"], "saree", "fashion_price", {}, [], None)
    add(s, "tumi amar sathe prem korba?", "romantic boundary again no overwrite", "block", [], ["saree_red_1", "saree_red_2"], "saree", "romantic_off_topic", {"risk_level": "low"}, [], None, 0.82)
    add(s, "second one er fabric ki?", "second saree still resolvable", "allow", ["saree_red_2"], ["saree_red_1", "saree_red_2"], "saree", "fashion_detail", {}, [], None)
    add(s, "amar mon kharap", "emotional low mood should not replace focus without products", "block", [], ["saree_red_1", "saree_red_2"], "saree", "emotional_low_mood", {"tone": "sad"}, [], None, 0.8)
    add(s, "etar sathe matching blouse ache?", "matching follow-up uses saree focus", "allow", ["saree_red_1"], ["blouse_1", "blouse_2"], "blouse", "fashion_cross_sell", {"category_key": "blouse"}, ["blouse_1", "blouse_2"], "blouse_1")
    add(s, "kichu valo dekhao", "vague shopping may write broad picks but not unsafe", "block", [], ["gift_1", "gift_2"], "blouse", "vague_shopping", {"budget_max": 3000}, ["gift_1", "gift_2"], "gift_1", 0.8)
    add(s, "first one er price?", "vague shopping product focus can be followed", "allow", ["gift_1"], ["gift_1", "gift_2"], "blouse", "fashion_price", {}, [], None)
    add(s, "blue panjabi ache?", "fresh panjabi request overrides gifts", "block", [], ["panjabi_blue_1"], "panjabi", "fashion_search", {"category_key": "panjabi", "color_family": "blue"}, ["panjabi_blue_1"], "panjabi_blue_1")

    # 3. Sensitive turns must not write memory.
    s = "S03_sensitive_guard"
    add(s, "ladies sandal dekhao", "new sandal focus", "block", [], ["sandal_l_1", "sandal_l_2"], "sandal", "fashion_search", {"category_key": "sandal"}, ["sandal_l_1", "sandal_l_2"], "sandal_l_1")
    add(s, "rash er jonno kon medicine khabo?", "medical advice blocked from memory", "block", [], ["sandal_l_1", "sandal_l_2"], "sandal", "medical_or_health_advice", {"risk_level": "high", "category_key": "wellness"}, ["bad_med_1"], "bad_med_1", 0.9, True)
    add(s, "etar price?", "sandal focus survives medical refusal", "allow", ["sandal_l_1"], ["sandal_l_1", "sandal_l_2"], "sandal", "fashion_price", {}, [], None)
    add(s, "case korle ki hobe?", "legal advice blocked", "block", [], ["sandal_l_1", "sandal_l_2"], "sandal", "legal_advice", {"risk_level": "high"}, [], None, 0.9, True)
    add(s, "second one ache?", "second sandal still resolves", "allow", ["sandal_l_2"], ["sandal_l_1", "sandal_l_2"], "sandal", "fashion_stock", {}, [], None)
    add(s, "kon party best?", "political blocked", "block", [], ["sandal_l_1", "sandal_l_2"], "sandal", "political", {"risk_level": "medium"}, [], None, 0.8, True)
    add(s, "etar size 38 ache?", "focus survives political boundary", "allow", ["sandal_l_1"], ["sandal_l_1", "sandal_l_2"], "sandal", "fashion_size_availability", {}, [], None)
    add(s, "ami more jabo", "crisis blocked and no shopping write", "block", [], ["sandal_l_1", "sandal_l_2"], "sandal", "self_harm_or_crisis", {"risk_level": "critical"}, [], None, 0.95, True)
    add(s, "kichu gift dekhao", "new explicit gift request can reset focus", "block", [], ["gift_safe_1"], "gift", "gift_recommendation", {"category_key": "gift"}, ["gift_safe_1"], "gift_safe_1", 0.8)
    add(s, "etar details dao", "new gift focus is usable", "allow", ["gift_safe_1"], ["gift_safe_1"], "gift", "fashion_detail", {}, [], None)

    # 4. Image-search memory and variant follow-up.
    s = "S04_image_memory"
    add(s, "[image upload: black polo]", "image exact writes longer focus", "block", [], ["polo_black", "polo_grey", "polo_white"], "shirt", "image_search", {"category_key": "shirt", "color_family": "black", "variant_group_id": "ribbed-polo"}, ["polo_black", "polo_grey", "polo_white"], "polo_black", 0.96, False, "image_search")
    add(s, "white ache?", "color-only follow-up uses image focus", "allow", ["polo_black"], ["polo_white"], "shirt", "image_search", {"category_key": "shirt", "color_family": "white", "variant_group_id": "ribbed-polo"}, ["polo_white"], "polo_white", 0.9, False, "image_search")
    add(s, "ar ki color ache?", "variant color listing uses focus", "allow", ["polo_white"], ["polo_white", "polo_black", "polo_grey"], "shirt", "image_search", {"category_key": "shirt", "variant_group_id": "ribbed-polo"}, ["polo_white", "polo_black", "polo_grey"], "polo_white", 0.9)
    add(s, "M size ache?", "size follow-up uses current polo", "allow", ["polo_white"], ["polo_white", "polo_black", "polo_grey"], "shirt", "fashion_size_availability", {}, [], None)
    add(s, "blue saree dekhao", "new category ignores image focus", "block", [], ["saree_blue_1"], "saree", "fashion_search", {"category_key": "saree", "color_family": "blue"}, ["saree_blue_1"], "saree_blue_1")
    add(s, "same design red ache?", "same-design now refers to saree, not polo", "allow", ["saree_blue_1"], ["saree_red_1"], "saree", "fashion_search", {"category_key": "saree", "color_family": "red", "variant_group_id": "saree-vg"}, ["saree_red_1"], "saree_red_1")
    add(s, "[image upload: weak/no match]", "low-confidence image should not overwrite focus", "block", [], ["saree_red_1"], "saree", "image_search", {"category_key": "unknown"}, ["bad_match"], "bad_match", 0.32, True, "image_search")
    add(s, "etar price?", "saree focus survives no-match image", "allow", ["saree_red_1"], ["saree_red_1"], "saree", "fashion_price", {}, [], None)
    add(s, "black shoe dekhao", "fresh shoe search", "block", [], ["shoe_1"], "shoe", "fashion_search", {"category_key": "shoe", "color_family": "black"}, ["shoe_1"], "shoe_1")
    add(s, "etar sathe matching belt ache?", "accessory follow-up uses shoe focus", "allow", ["shoe_1"], ["belt_1"], "belt", "fashion_cross_sell", {"category_key": "belt"}, ["belt_1"], "belt_1")

    # 5. Expiry and stale client context.
    s = "S05_expiry"
    add(s, "green kameez dekhao", "new kameez focus", "block", [], ["kameez_green_1"], "kameez", "fashion_search", {"category_key": "kameez", "color_family": "green"}, ["kameez_green_1"], "kameez_green_1")
    add(s, "etar price koto?", "fresh follow-up works", "allow", ["kameez_green_1"], ["kameez_green_1"], "kameez", "fashion_price", {}, [], None)
    add(s, "etar stock ache?", "expired focus should block", "expired", [], ["kameez_green_1"], "kameez", "fashion_stock", {}, [], None, age_focus_minutes_before=120)
    add(s, "green kameez ta abar dekhao", "explicit kameez re-establishes focus", "block", [], ["kameez_green_1"], "kameez", "fashion_search", {"category_key": "kameez", "color_family": "green"}, ["kameez_green_1"], "kameez_green_1")
    add(s, "last one er dam?", "last resolves when fresh", "allow", ["kameez_green_1"], ["kameez_green_1"], "kameez", "fashion_price", {}, [], None)
    add(s, "delivery charge koto?", "delivery policy question must not use product focus", "block", [], ["kameez_green_1"], "kameez", "delivery_query", {}, [], None)
    add(s, "etar size ache?", "focus still available after delivery question", "allow", ["kameez_green_1"], ["kameez_green_1"], "kameez", "fashion_size_availability", {}, [], None)
    add(s, "order status kothay?", "order support must not use product focus", "block", [], ["kameez_green_1"], "kameez", "order_tracking_support", {}, [], None)
    add(s, "eta order korte chai", "explicit product order follow-up uses focus", "allow", ["kameez_green_1"], ["kameez_green_1"], "kameez", "cart_add", {}, [], None)
    add(s, "kid frock dekhao", "fresh frock overrides kameez", "block", [], ["frock_1"], "frock", "fashion_search", {"category_key": "frock"}, ["frock_1"], "frock_1")

    # 6. Preference promotion and category override.
    s = "S06_preferences"
    add(s, "red saree dekhao", "red count 1", "block", [], ["saree_red_a"], "saree", "fashion_search", {"category_key": "saree", "color_family": "red"}, ["saree_red_a"], "saree_red_a")
    add(s, "red kameez ache?", "fresh kameez not old saree", "block", [], ["kameez_red_a"], "kameez", "fashion_search", {"category_key": "kameez", "color_family": "red"}, ["kameez_red_a"], "kameez_red_a")
    add(s, "red panjabi ache?", "fresh panjabi, red count reaches 3", "block", [], ["panjabi_red_a"], "panjabi", "fashion_search", {"category_key": "panjabi", "color_family": "red"}, ["panjabi_red_a"], "panjabi_red_a")
    add(s, "kichu valo dekhao", "vague should not force old panjabi product", "block", [], ["general_1", "general_2"], "panjabi", "vague_shopping", {}, ["general_1", "general_2"], "general_1", 0.8)
    add(s, "first one er price?", "general product focus works", "allow", ["general_1"], ["general_1", "general_2"], "panjabi", "fashion_price", {}, [], None)
    add(s, "blue shirt dekhao", "new shirt overrides preferences", "block", [], ["shirt_blue_1"], "shirt", "fashion_search", {"category_key": "shirt", "color_family": "blue"}, ["shirt_blue_1"], "shirt_blue_1")
    add(s, "etar color blue?", "follow-up shirt detail", "allow", ["shirt_blue_1"], ["shirt_blue_1"], "shirt", "fashion_detail", {}, [], None)
    add(s, "5000 er moddhe dekhao", "budget-only follow-up can use active filters, not product ID", "block", [], ["shirt_budget_1"], "shirt", "fashion_search", {"category_key": "shirt", "budget_max": 5000}, ["shirt_budget_1"], "shirt_budget_1")
    add(s, "etar price?", "budget result focus works", "allow", ["shirt_budget_1"], ["shirt_budget_1"], "shirt", "fashion_price", {}, [], None)
    add(s, "saree under 7000", "new saree overrides shirt but carries budget concept", "block", [], ["saree_7000_1"], "saree", "fashion_search", {"category_key": "saree", "budget_max": 7000}, ["saree_7000_1"], "saree_7000_1")

    # 7. Bangla flow.
    s = "S07_bangla"
    add(s, "লাল শাড়ি দেখাও", "Bangla new request", "block", [], ["bn_saree_1", "bn_saree_2"], "saree", "fashion_search", {"category_key": "saree", "color_family": "red"}, ["bn_saree_1", "bn_saree_2"], "bn_saree_1")
    add(s, "এটার দাম কত?", "Bangla pronoun price", "allow", ["bn_saree_1"], ["bn_saree_1", "bn_saree_2"], "saree", "fashion_price", {}, [], None)
    add(s, "দ্বিতীয়টার সাইজ আছে?", "Bangla ordinal second", "allow", ["bn_saree_2"], ["bn_saree_1", "bn_saree_2"], "saree", "fashion_size_availability", {}, [], None)
    add(s, "আর কালার আছে?", "Bangla color follow-up", "allow", ["bn_saree_1"], ["bn_saree_blue"], "saree", "fashion_search", {"category_key": "saree", "color_family": "blue"}, ["bn_saree_blue"], "bn_saree_blue")
    add(s, "কালো পাঞ্জাবি দেখাও", "Bangla fresh category switch", "block", [], ["bn_panjabi_1"], "panjabi", "fashion_search", {"category_key": "panjabi", "color_family": "black"}, ["bn_panjabi_1"], "bn_panjabi_1")
    add(s, "এটা অর্ডার করবো", "Bangla order follow-up", "allow", ["bn_panjabi_1"], ["bn_panjabi_1"], "panjabi", "cart_add", {}, [], None)
    add(s, "আমার মন খারাপ", "Bangla emotional detour blocked from write", "block", [], ["bn_panjabi_1"], "panjabi", "emotional_low_mood", {"tone": "sad"}, [], None, 0.8)
    add(s, "এটার দাম?", "Panjabi survives emotional detour", "allow", ["bn_panjabi_1"], ["bn_panjabi_1"], "panjabi", "fashion_price", {}, [], None)
    add(s, "আইনি পরামর্শ লাগবে", "Bangla legal blocked", "block", [], ["bn_panjabi_1"], "panjabi", "legal_advice", {"risk_level": "high"}, [], None, 0.9, True)
    add(s, "সাদা স্যান্ডেল দেখাও", "Bangla fresh sandal", "block", [], ["bn_sandal_1"], "sandal", "fashion_search", {"category_key": "sandal", "color_family": "white"}, ["bn_sandal_1"], "bn_sandal_1")

    # 8. English flow.
    s = "S08_english"
    add(s, "show me long sleeve shirts under 4000", "English new shirt", "block", [], ["shirt_long_1", "shirt_long_2"], "shirt", "fashion_search", {"category_key": "shirt", "budget_max": 4000}, ["shirt_long_1", "shirt_long_2"], "shirt_long_1")
    add(s, "how much is this?", "English this resolves primary", "allow", ["shirt_long_1"], ["shirt_long_1", "shirt_long_2"], "shirt", "fashion_price", {}, [], None)
    add(s, "does the second one have XL?", "English second resolves alt", "allow", ["shirt_long_2"], ["shirt_long_1", "shirt_long_2"], "shirt", "fashion_size_availability", {}, [], None)
    add(s, "show similar cheaper", "alternative follow-up uses context", "allow", ["shirt_long_2"], ["shirt_cheaper_1"], "shirt", "fashion_search", {"category_key": "shirt", "budget_max": 3000}, ["shirt_cheaper_1"], "shirt_cheaper_1")
    add(s, "do you have pearl earrings?", "fresh earrings request", "block", [], ["earring_1"], "earring", "fashion_search", {"category_key": "earring"}, ["earring_1"], "earring_1")
    add(s, "what goes with this?", "cross-sell uses earrings", "allow", ["earring_1"], ["necklace_1"], "necklace", "fashion_cross_sell", {"category_key": "necklace"}, ["necklace_1"], "necklace_1")
    add(s, "where is my order?", "order tracking no product memory", "block", [], ["necklace_1"], "necklace", "order_tracking_support", {}, [], None)
    add(s, "tell me more about it", "necklace focus survived order support", "allow", ["necklace_1"], ["necklace_1"], "necklace", "fashion_detail", {}, [], None)
    add(s, "best phone under 20k?", "off-category tech should not use necklace", "block", [], ["necklace_1"], "necklace", "random_tech", {}, [], None)
    add(s, "show me handbags", "fresh handbag", "block", [], ["bag_1"], "bag", "fashion_search", {"category_key": "bag"}, ["bag_1"], "bag_1")

    # 9. Ambiguous/off-topic nouns with fact words.
    s = "S09_ambiguity"
    add(s, "blue bag dekhao", "new bag focus", "block", [], ["bag_blue_1"], "bag", "fashion_search", {"category_key": "bag", "color_family": "blue"}, ["bag_blue_1"], "bag_blue_1")
    add(s, "kachchi biryani ache?", "food query must not use bag focus", "block", [], ["bag_blue_1"], "bag", "unknown_fallback", {}, [], None, 0.7)
    add(s, "amar boyosh koto?", "personal random koto must not use bag focus", "block", [], ["bag_blue_1"], "bag", "unknown_fallback", {}, [], None, 0.7)
    add(s, "delivery charge koto?", "delivery question no product focus", "block", [], ["bag_blue_1"], "bag", "delivery_query", {}, [], None)
    add(s, "eta ki leather?", "explicit eta uses bag", "allow", ["bag_blue_1"], ["bag_blue_1"], "bag", "fashion_detail", {}, [], None)
    add(s, "do you sell laptop?", "fresh unsupported product no bag memory", "block", [], ["bag_blue_1"], "bag", "random_tech", {}, [], None)
    add(s, "available?", "one-word availability can use current bag", "allow", ["bag_blue_1"], ["bag_blue_1"], "bag", "fashion_stock", {}, [], None)
    add(s, "do you have black belt?", "fresh belt request", "block", [], ["belt_black_1"], "belt", "fashion_search", {"category_key": "belt", "color_family": "black"}, ["belt_black_1"], "belt_black_1")
    add(s, "tui stupid", "abuse no write", "block", [], ["belt_black_1"], "belt", "abusive_mild", {"risk_level": "medium"}, [], None, 0.8, True)
    add(s, "etar price?", "belt focus survives abuse", "allow", ["belt_black_1"], ["belt_black_1"], "belt", "fashion_price", {}, [], None)

    # 10. Low confidence and no-match safety.
    s = "S10_low_confidence"
    add(s, "brown bag dekhao", "new bag focus", "block", [], ["bag_brown_1", "bag_brown_2"], "bag", "fashion_search", {"category_key": "bag", "color_family": "brown"}, ["bag_brown_1", "bag_brown_2"], "bag_brown_1")
    add(s, "etar price?", "fresh bag focus", "allow", ["bag_brown_1"], ["bag_brown_1", "bag_brown_2"], "bag", "fashion_price", {}, [], None)
    add(s, "maybe same item?", "low-confidence response must not overwrite", "block", [], ["bag_brown_1", "bag_brown_2"], "bag", "fashion_search", {"category_key": "bag"}, ["wrong_low_1"], "wrong_low_1", 0.42, True)
    add(s, "second one er price?", "old second bag still resolves", "allow", ["bag_brown_2"], ["bag_brown_1", "bag_brown_2"], "bag", "fashion_price", {}, [], None)
    add(s, "[image upload: unclear]", "low confidence image no overwrite", "block", [], ["bag_brown_1", "bag_brown_2"], "bag", "image_search", {"category_key": "unknown"}, ["bad_img"], "bad_img", 0.2, True, "image_search")
    add(s, "etar stock?", "old bag primary still resolves", "allow", ["bag_brown_1"], ["bag_brown_1", "bag_brown_2"], "bag", "fashion_stock", {}, [], None)
    add(s, "green frock dekhao", "new frock focus", "block", [], ["frock_green_1"], "frock", "fashion_search", {"category_key": "frock", "color_family": "green"}, ["frock_green_1"], "frock_green_1")
    add(s, "same color shoe ache?", "new shoe category should not use frock despite same color phrase", "block", [], ["shoe_green_1"], "shoe", "fashion_search", {"category_key": "shoe", "color_family": "green"}, ["shoe_green_1"], "shoe_green_1")
    add(s, "etar size?", "shoe focus works", "allow", ["shoe_green_1"], ["shoe_green_1"], "shoe", "fashion_size_availability", {}, [], None)
    add(s, "third one details?", "no third should not invent", "allow", [], ["shoe_green_1"], "shoe", "fashion_detail", {}, [], None)

    if len(cases) != 100:
        raise AssertionError(f"Expected 100 cases, got {len(cases)}")
    return cases


def run_eval(cases: list[MemoryTurnCase]) -> list[MemoryEvalResult]:
    ontology = ProductOntology()
    resolver = InventoryMemoryResolver(ontology)
    results: list[MemoryEvalResult] = []
    with TemporaryDirectory() as tmp_dir:
        store = ConversationStateStore(db_path=Path(tmp_dir) / "state.sqlite")
        current_scenario: str | None = None
        session_id = ""

        for case in cases:
            if case.scenario_id != current_scenario:
                current_scenario = case.scenario_id
                session_id = f"eval-{case.scenario_id}"
                store.clear(session_id)

            state = store.get(session_id)
            if case.age_focus_minutes_before is not None and state.turn_count > 0:
                age_focus(state, minutes=case.age_focus_minutes_before)
                store.save(state)
                state = store.get(session_id)

            policy = should_use_product_focus(question=case.user, state=state, ontology=ontology)
            request = InventoryAskRequest(question=case.user, session_id=session_id)
            hydrated = hydrate_request_from_state(request=request, state=state, ontology=ontology)
            resolved = resolver.resolve(
                question=hydrated.request.question,
                filters=hydrated.request.filters.model_copy(deep=True),
                focused_product_ids=hydrated.request.focused_product_ids,
                active_filters=hydrated.request.active_filters,
                last_answer_plan=hydrated.request.last_answer_plan,
            )

            new_state = store.record_turn(
                session_id=session_id,
                question=case.user,
                intent=case.response_intent,
                slots=case.response_slots,
                product_ids=case.response_product_ids,
                primary_product_id=case.response_primary_product_id,
                confidence=case.response_confidence,
                abstained=case.response_abstained,
                memory_source=case.memory_source,
                write_reason=f"memory_flow_eval:{case.case_id}",
            )

            failures: list[str] = []
            if case.expected_policy == "allow" and not policy.allowed:
                failures.append(f"Expected memory policy allow, got block: {policy.reason}")
            if case.expected_policy == "block" and policy.allowed:
                failures.append("Expected memory policy block, got allow")
            if case.expected_policy == "expired" and not policy.expired:
                failures.append(f"Expected expired focus, got expired={policy.expired}, reason={policy.reason}")
            if case.expected_resolved_ids != resolved.resolution.resolved_product_ids:
                failures.append(
                    f"Expected resolved IDs {case.expected_resolved_ids}, got {resolved.resolution.resolved_product_ids}"
                )
            if case.expected_focus_after is not None and new_state.last_shown_product_ids != case.expected_focus_after:
                failures.append(
                    f"Expected focus after {case.expected_focus_after}, got {new_state.last_shown_product_ids}"
                )
            actual_category = new_state.active_slots.get("category_key")
            if case.expected_category_after is not None and actual_category != case.expected_category_after:
                failures.append(
                    f"Expected category after {case.expected_category_after}, got {actual_category}"
                )

            results.append(
                MemoryEvalResult(
                    case_id=case.case_id,
                    scenario_id=case.scenario_id,
                    turn=case.turn,
                    user=case.user,
                    passed=not failures,
                    failures=failures,
                    expected_policy=case.expected_policy,
                    actual_policy_allowed=policy.allowed,
                    actual_policy_expired=policy.expired,
                    policy_reason=policy.reason,
                    hydrated_used_state=hydrated.used_state,
                    hydration_reason=hydrated.reason,
                    resolved_ids=resolved.resolution.resolved_product_ids,
                    used_memory=resolved.resolution.used_memory,
                    ignored_memory_reason=resolved.resolution.ignored_memory_reason,
                    focus_after=list(new_state.last_shown_product_ids),
                    category_after=new_state.active_slots.get("category_key"),
                )
            )

    return results


def age_focus(state: Any, *, minutes: int) -> None:
    updated = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    state.product_focus_updated_at = to_iso(updated)
    ttl = state.product_focus_ttl_seconds or 1800
    state.product_focus_expires_at = to_iso(updated + timedelta(seconds=ttl))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(path: Path, cases: list[MemoryTurnCase], results: list[MemoryEvalResult]) -> None:
    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed
    scenario_totals: dict[str, tuple[int, int]] = {}
    for result in results:
        total, ok = scenario_totals.get(result.scenario_id, (0, 0))
        scenario_totals[result.scenario_id] = (total + 1, ok + int(result.passed))

    lines = [
        "# Memory Flow 100-Case Evaluation",
        "",
        f"- Created: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Total cases: **{len(results)}**",
        f"- Passed: **{passed}**",
        f"- Failed: **{failed}**",
        "",
        "## Scenario Summary",
        "",
        "| Scenario | Passed | Total |",
        "|---|---:|---:|",
    ]
    for scenario_id, (total, ok) in scenario_totals.items():
        lines.append(f"| `{scenario_id}` | {ok} | {total} |")

    lines.extend(["", "## Failed Cases", ""])
    failed_results = [result for result in results if not result.passed]
    if not failed_results:
        lines.append("No failed cases.")
    else:
        for result in failed_results:
            lines.extend(
                [
                    f"### {result.case_id}",
                    "",
                    f"- User: `{result.user}`",
                    f"- Expected policy: `{result.expected_policy}`",
                    f"- Actual policy: allowed=`{result.actual_policy_allowed}`, expired=`{result.actual_policy_expired}`",
                    f"- Policy reason: {result.policy_reason}",
                    f"- Resolved IDs: `{result.resolved_ids}`",
                    "- Failures:",
                    *[f"  - {failure}" for failure in result.failures],
                    "",
                ]
            )

    lines.extend(
        [
            "",
            "## Full Case Table",
            "",
            "| Case | User | Expected | Actual | Resolved | Result |",
            "|---|---|---|---|---|---|",
        ]
    )
    for result in results:
        actual = "expired" if result.actual_policy_expired else "allow" if result.actual_policy_allowed else "block"
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"| `{result.case_id}` | {result.user} | {result.expected_policy} | {actual} | {', '.join(result.resolved_ids) or '-'} | {status} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 100-case multi-turn memory flow evaluation.")
    parser.add_argument("--cases-out", default="evaluation/memory_multiturn_100_cases.jsonl")
    parser.add_argument("--results-out", default="results/memory_flow_100_eval.jsonl")
    parser.add_argument("--report-out", default="results/memory_flow_100_eval.md")
    args = parser.parse_args()

    cases = build_cases()
    results = run_eval(cases)

    write_jsonl(Path(args.cases_out), [asdict(case) for case in cases])
    write_jsonl(Path(args.results_out), [asdict(result) for result in results])
    write_report(Path(args.report_out), cases, results)

    failed = [result for result in results if not result.passed]
    print(f"Memory flow eval: {len(results) - len(failed)}/{len(results)} passed")
    if failed:
        for result in failed[:20]:
            print(f"FAIL {result.case_id}: {'; '.join(result.failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
