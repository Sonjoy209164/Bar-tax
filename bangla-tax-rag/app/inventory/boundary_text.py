"""
Shared text utilities for the conversation entry layer.

Kept tiny on purpose. The goal is that detection logic lives in
safety_rules.py (regex-allowed) and boundary_classifier.py (LLM-first); this
file only owns the normalization + token-boundary matching primitives that
both consume.
"""
from __future__ import annotations

import re

BANGLA_TEXT_PATTERN = re.compile(r"[ঀ-৿]")
BANGLA_DIGIT_TRANS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

_BANGLISH_MARKERS: tuple[str, ...] = (
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
    "biye",
    "mon kharap",
)


def normalize(text: str) -> str:
    """Casefold, transliterate Bangla digits, strip punctuation, collapse spaces."""
    lowered = text.casefold().translate(BANGLA_DIGIT_TRANS).replace("&", " and ")
    stripped = re.sub(r"[^a-z0-9ঀ-৿.\s+-]", " ", lowered)
    return " ".join(stripped.split())


def detect_language(text: str) -> str:
    """Returns 'bangla' | 'banglish' | 'english'."""
    if BANGLA_TEXT_PATTERN.search(text):
        return "bangla"
    normalized = normalize(text)
    return "banglish" if has_any(normalized, _BANGLISH_MARKERS) else "english"


def has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_has_phrase(text, phrase) for phrase in phrases)


def matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _has_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = normalize(phrase)
    if not normalized_phrase:
        return False
    pattern = re.escape(normalized_phrase).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text))


__all__ = ["normalize", "detect_language", "has_any", "matches_any"]
