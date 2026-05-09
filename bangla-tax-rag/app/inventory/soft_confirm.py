"""
Confidence-aware soft-confirm response decoration.

When the bot is moderately confident (between MEDIUM_CONFIDENCE and
HIGH_CONFIDENCE), it should still answer — but append a one-line
soft confirmation so the customer can correct course quickly:

  "এটাই খুঁজছিলেন, না অন্য কিছু?"
  "Was that what you were looking for, or something else?"

This is purely a presentation-layer decorator. It never blocks the answer.
"""
from __future__ import annotations

from app.inventory.clarification import HIGH_CONFIDENCE, MEDIUM_CONFIDENCE


def needs_soft_confirm(confidence: float, intent: str) -> bool:
    """
    Soft-confirm zone: confidence in (MEDIUM, HIGH) for fashion search-style
    intents. Skip for variant/size/policy/order — those are already focused.
    """
    if intent in {
        "fashion_variant_color",
        "fashion_size_availability",
        "fashion_accessory_match",
        "fashion_compare",
        "fashion_styling_advice",
        "fashion_clarification",
    }:
        return False
    if intent.startswith("policy_") or intent.startswith("order_"):
        return False
    return MEDIUM_CONFIDENCE <= confidence < HIGH_CONFIDENCE


def soft_confirm_suffix(language: str = "english") -> str:
    """Localized soft-confirm tail."""
    table = {
        "bangla": "এটাই খুঁজছিলেন, নাকি অন্য কিছু?",
        "banglish": "Eta-i khujchilen, naki onno kichu?",
        "english": "Was that what you were looking for, or something else?",
    }
    return table.get(language, table["english"])


def decorate_with_soft_confirm(answer: str, *, confidence: float, intent: str, language: str) -> str:
    """Append a soft-confirm tail to `answer` if we're in the medium zone."""
    if not needs_soft_confirm(confidence, intent):
        return answer
    suffix = soft_confirm_suffix(language)
    if suffix in answer:
        return answer
    sep = "" if answer.endswith(("\n", "?", ".", "।", "!")) else "."
    return f"{answer}{sep} {suffix}"
