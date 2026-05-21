"""
Coreference resolution: turn pronouns into product IDs.

Customer says "এটার দাম কত?" or "first one ta dekhao" — the bot needs to know
WHICH product they mean. We resolve against the conversation state's
`last_shown_product_ids`.

This is a simple deterministic resolver, not a full NLP coreference model.
It covers the patterns customers actually use in Bangla / Banglish / English
shopping conversations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Pronouns and demonstratives that mean "the thing we just talked about".
_THIS_PHRASES = (
    "এটা", "এটি", "এটির", "এটার", "এই টা", "এই", "ইহা",
    "eta", "etar", "etir", "eti", "eita", "eitar", "ei ta", "this", "this one", "it",
)

_THAT_PHRASES = (
    "ওটা", "ওটি", "ওটির", "ওটার", "ওই", "সেটা", "সেটার", "সেটি",
    "তার", "এর",
    "ota", "otar", "oti", "oita", "oitar", "oi", "seta", "shetar", "tar", "er", "that", "that one",
)

# Ordinal references — "first one", "second", "প্রথম টা"
_FIRST_PHRASES = (
    "first", "first one", "1st", "প্রথম", "প্রথমটা", "prothom", "prothom ta",
)
_SECOND_PHRASES = (
    "second", "second one", "2nd", "দ্বিতীয়", "দ্বিতীয়টা", "ditiyo", "dwitiyo", "ditiyo ta",
)
_THIRD_PHRASES = (
    "third", "third one", "3rd", "তৃতীয়", "তৃতীয়টা", "tritiyo", "tritiyo ta",
)
_LAST_PHRASES = (
    "last", "last one", "শেষ", "শেষেরটা", "shesh", "shesh ta",
)

# Reference to the same design without the demonstrative
_SAME_DESIGN_PHRASES = (
    "same design", "same one", "same ta", "same er", "ei design",
    "same design e", "same design er", "একই ডিজাইন", "একই", "এই ডিজাইন",
)


@dataclass(frozen=True)
class CoreferenceResult:
    resolved_product_id: str | None
    resolution_type: str  # "this", "that", "ordinal:1", "ordinal:last", "same_design", "none"
    matched_phrase: str | None = None


def resolve_coreference(
    *,
    question: str,
    last_shown_product_ids: list[str],
    last_primary_product_id: str | None = None,
) -> CoreferenceResult:
    """
    Detect a pronoun / demonstrative / ordinal in `question` and map it to a
    product_id from the recent conversation context.

    Returns CoreferenceResult with `resolved_product_id=None` when no
    pronoun is found or the context is empty.
    """
    if not last_shown_product_ids and last_primary_product_id is None:
        return CoreferenceResult(resolved_product_id=None, resolution_type="none")

    text = question.lower().strip()

    # Ordinals first — they're more specific than "this"
    matched, idx = _match_ordinal(text, last_shown_product_ids)
    if matched is not None and last_shown_product_ids:
        return CoreferenceResult(
            resolved_product_id=last_shown_product_ids[idx],
            resolution_type=f"ordinal:{matched}",
            matched_phrase=matched,
        )

    # Demonstratives → primary or first shown
    for phrase in _THIS_PHRASES + _THAT_PHRASES + _SAME_DESIGN_PHRASES:
        if _word_match(text, phrase):
            target = last_primary_product_id or (
                last_shown_product_ids[0] if last_shown_product_ids else None
            )
            if target:
                resolution_type = (
                    "same_design" if phrase in _SAME_DESIGN_PHRASES
                    else "that" if phrase in _THAT_PHRASES
                    else "this"
                )
                return CoreferenceResult(
                    resolved_product_id=target,
                    resolution_type=resolution_type,
                    matched_phrase=phrase,
                )

    return CoreferenceResult(resolved_product_id=None, resolution_type="none")


def _match_ordinal(text: str, products: list[str]) -> tuple[str | None, int]:
    """Return (matched_phrase, index_into_products) or (None, -1)."""
    for phrase in _FIRST_PHRASES:
        if _word_match(text, phrase):
            return ("1st", 0) if products else (None, -1)
    for phrase in _SECOND_PHRASES:
        if _word_match(text, phrase) and len(products) >= 2:
            return ("2nd", 1)
    for phrase in _THIRD_PHRASES:
        if _word_match(text, phrase) and len(products) >= 3:
            return ("3rd", 2)
    for phrase in _LAST_PHRASES:
        if _word_match(text, phrase) and products:
            return ("last", len(products) - 1)
    return (None, -1)


def _word_match(text: str, phrase: str) -> bool:
    """
    Match phrase as a whole word (or whole multi-word sequence). Avoids
    matching "this" inside "thistle" or "eta" inside "metar".
    """
    if not phrase:
        return False
    # For Bangla characters, simple substring match is fine — those scripts
    # don't form compound words from these tokens the way ASCII does.
    if any(ord(c) > 0x0980 for c in phrase):
        return phrase in text
    pattern = r"(?:^|\b|\s)" + re.escape(phrase) + r"(?:\b|\s|$|[?.,!])"
    return re.search(pattern, text) is not None
