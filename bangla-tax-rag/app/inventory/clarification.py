"""
Clarification policy for the fashion retail assistant.

When the bot is too uncertain or has too few slots to give a useful answer,
ask one focused question instead of dumping random products. The clarification
is generated in the customer's language so it feels natural.

Decision matrix:
  confidence >= 0.85                          → answer normally
  0.65 <= confidence < 0.85 AND slots >= 1    → answer, but consider soft-confirm
  confidence < 0.65 AND no concrete slot      → ask clarification
  confidence < 0.50                           → ask clarification
  too many matches (>15) AND no narrowing slot → ask clarification

The module returns a single ClarificationDecision telling the caller exactly
what to do next.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.inventory.fashion_retail import FashionRetailSlots

# Thresholds — kept in one place so they're easy to tune from feedback data.
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.65
LOW_CONFIDENCE = 0.50
TOO_MANY_MATCHES = 15


@dataclass(frozen=True)
class ClarificationDecision:
    should_clarify: bool
    question: str | None = None
    reason: str | None = None
    missing_slot: str | None = None


def decide_clarification(
    *,
    slots: FashionRetailSlots,
    total_matches: int,
) -> ClarificationDecision:
    """
    Decide whether to clarify. Returns a structured decision; the caller
    builds the response based on `should_clarify`.
    """
    # Override: if customer asked an explicit policy/order question, never clarify
    # — those have their own dedicated handlers.
    if slots.intent.startswith("policy_") or slots.intent.startswith("order_"):
        return ClarificationDecision(should_clarify=False)

    has_concrete = _has_concrete_slot(slots)
    confidence = slots.confidence

    # Very low confidence — always ask
    if confidence < LOW_CONFIDENCE:
        question, missing = _craft_clarification(slots)
        return ClarificationDecision(
            should_clarify=True,
            question=question,
            reason=f"low_confidence:{confidence:.2f}",
            missing_slot=missing,
        )

    # Mid confidence with no concrete slot — ask
    if confidence < MEDIUM_CONFIDENCE and not has_concrete:
        question, missing = _craft_clarification(slots)
        return ClarificationDecision(
            should_clarify=True,
            question=question,
            reason="medium_confidence_no_slots",
            missing_slot=missing,
        )

    # Too many matches and no narrowing signal — ask one filter question
    if total_matches > TOO_MANY_MATCHES and _is_too_broad(slots):
        question, missing = _craft_clarification(slots)
        return ClarificationDecision(
            should_clarify=True,
            question=question,
            reason=f"too_broad:{total_matches}_matches",
            missing_slot=missing,
        )

    return ClarificationDecision(should_clarify=False)


def _has_concrete_slot(slots: FashionRetailSlots) -> bool:
    return any([
        slots.category_key,
        slots.color_family,
        slots.fabric,
        slots.work_type,
        slots.size,
        slots.occasion,
        slots.budget_max is not None,
        slots.budget_min is not None,
        slots.design_id,
    ])


def _is_too_broad(slots: FashionRetailSlots) -> bool:
    """
    True when only category is known and no other narrowing signal exists.
    Showing 50 sarees with no color/fabric/budget is not helpful.
    """
    narrowing_signals = [
        slots.color_family,
        slots.fabric,
        slots.work_type,
        slots.occasion,
        slots.budget_max,
        slots.size,
    ]
    return slots.category_key is not None and not any(narrowing_signals)


def _craft_clarification(slots: FashionRetailSlots) -> tuple[str, str]:
    """
    Pick the most useful follow-up question + name the missing slot.
    Question is rendered in the customer's detected language.
    """
    lang = slots.language or "english"

    # Priority order: category > occasion > color > budget > fabric
    if not slots.category_key:
        return _question_for("category", lang), "category"

    if not slots.occasion and not slots.color_family:
        return _question_for("occasion_or_color", lang, slots), "occasion_or_color"

    if not slots.color_family:
        return _question_for("color", lang, slots), "color"

    if not slots.budget_max:
        return _question_for("budget", lang, slots), "budget"

    if not slots.fabric and slots.category_key in {"saree", "blouse", "panjabi", "kurti"}:
        return _question_for("fabric", lang, slots), "fabric"

    # Fallback — generic
    return _question_for("generic", lang, slots), "generic"


def _question_for(slot: str, lang: str, slots: FashionRetailSlots | None = None) -> str:
    """Localized clarification questions."""
    cat = (slots.category_label.lower() if slots and slots.category_label else "item") if slots else "item"

    questions = {
        "category": {
            "bangla": "কোন ধরনের পোশাক খুঁজছেন? শাড়ি, পাঞ্জাবি, কুর্তি, নাকি অন্য কিছু?",
            "banglish": "Kon dhoroner pošak khujchen? Saree, panjabi, kurti, naki onno kichu?",
            "english": "What kind of item are you looking for — saree, panjabi, kurti, or something else?",
        },
        "occasion_or_color": {
            "bangla": f"কোন অনুষ্ঠানের জন্য {cat} খুঁজছেন, আর কোন রঙ পছন্দ?",
            "banglish": f"Kon occasion-er jonno {cat} khujchen, ar kon rong pochonddo?",
            "english": f"What occasion is the {cat} for, and any preferred color?",
        },
        "color": {
            "bangla": f"কোন রঙের {cat} পছন্দ — লাল, নীল, সবুজ, কালো, নাকি অন্য কিছু?",
            "banglish": f"Kon ronger {cat} pochonddo — laal, neel, sobuj, kalo, naki onno kichu?",
            "english": f"Any preferred color for the {cat} — red, blue, green, black, or something else?",
        },
        "budget": {
            "bangla": f"আপনার বাজেট কত? তাহলে আমি সেই দামের মধ্যে {cat} দেখাতে পারব।",
            "banglish": f"Apnar budget koto? Tahole ami sei damer moddhe {cat} dekhate parbo.",
            "english": f"What's your budget? I'll show {cat} in that range.",
        },
        "fabric": {
            "bangla": f"কোন কাপড়ের {cat} খুঁজছেন — জামদানি, কাতান, সিল্ক, কটন?",
            "banglish": f"Kon kapor-er {cat} khujchen — jamdani, katan, silk, cotton?",
            "english": f"Which fabric do you prefer for the {cat} — jamdani, katan, silk, or cotton?",
        },
        "generic": {
            "bangla": "একটু বিস্তারিত বলবেন? রঙ, সাইজ, বাজেট, বা অনুষ্ঠানের কথা জানালে সাহায্য করতে পারব।",
            "banglish": "Ektu bistarito bolben? Rong, size, budget, ba occasion janalei sahajjo korte parbo.",
            "english": "Could you share a bit more — color, size, budget, or occasion would help me find the right one.",
        },
    }
    bucket = questions.get(slot, questions["generic"])
    return bucket.get(lang, bucket["english"])
