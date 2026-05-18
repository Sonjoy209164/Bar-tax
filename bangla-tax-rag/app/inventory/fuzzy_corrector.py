"""
Fuzzy token correction for romanized Bangla fashion vocabulary.

Handles typos and novel misspellings that the Banglish normalizer misses
because it only knows exact patterns.  For example:
  "jamdhani" → "jamdani"
  "georgett" → "georgette"
  "weeding"  → "wedding"
  "panjab"   → "panjabi"

Uses difflib.get_close_matches (no extra deps).  Fast enough for per-request
use on short text (avg < 1 ms per query on typical inputs).
"""
from __future__ import annotations

import re
from difflib import get_close_matches

# ---------------------------------------------------------------------------
# Vocabulary: all canonical romanized terms the system understands.
# Grouped by domain — only the terms worth correcting to.
# ---------------------------------------------------------------------------
_CATEGORIES = [
    "saree", "sari", "panjabi", "kurti", "salwar", "lehenga", "blouse",
    "jewelry", "bag", "shoes", "watch", "cosmetics", "fragrance",
]

_FABRICS = [
    "jamdani", "katan", "muslin", "silk", "cotton", "georgette", "chiffon",
    "linen", "denim", "velvet", "crepe", "organza", "net",
]

_WORK_TYPES = [
    "zari", "meena", "embroidery", "block_print", "buti", "nakshi",
    "printed", "plain", "hand_woven", "banarasi",
]

_OCCASIONS = [
    "wedding", "eid", "puja", "boishakh", "office", "casual",
    "birthday", "anniversary", "party",
]

_COLORS = [
    "red", "blue", "green", "black", "white", "gold", "silver", "maroon",
    "navy", "pink", "purple", "orange", "yellow", "brown", "grey", "gray",
    "beige", "cream", "turquoise", "magenta", "olive", "coral",
]

_SIZES = ["xs", "small", "medium", "large", "xlarge", "xxlarge"]

# Flat vocabulary for matching
_VOCABULARY: list[str] = (
    _CATEGORIES + _FABRICS + _WORK_TYPES + _OCCASIONS + _COLORS + _SIZES
)

# Pre-built lower-cased set for fast membership check (skip words already correct)
_VOCAB_SET: set[str] = set(_VOCABULARY)

# Minimum token length to attempt correction (don't correct "of", "to", "is")
_MIN_TOKEN_LEN = 4
# difflib cutoff — 0.75 avoids false positives (e.g. "lotus"→"blouse") while
# catching real typos like "weeding"→"wedding" (ratio 0.857)
_CUTOFF = 0.75


def fuzzy_correct_token(token: str) -> str:
    """
    Return the best-matching vocabulary term for a single token, or the
    original token if no close match is found.
    """
    lower = token.lower()
    if lower in _VOCAB_SET or len(lower) < _MIN_TOKEN_LEN:
        return token
    matches = get_close_matches(lower, _VOCABULARY, n=1, cutoff=_CUTOFF)
    return matches[0] if matches else token


def fuzzy_correct_text(text: str) -> str:
    """
    Apply token-level fuzzy correction to a full query string.
    Non-ASCII tokens (Bangla Unicode) are left untouched.
    Returns the corrected string, which may be identical to the input.
    """
    # Split on whitespace, preserving separators
    tokens = re.split(r"(\s+)", text)
    corrected: list[str] = []
    changed = False
    for tok in tokens:
        if not tok.strip():          # whitespace segment — keep as-is
            corrected.append(tok)
            continue
        # Skip Bangla Unicode tokens
        if any(ord(c) > 0x0980 for c in tok):
            corrected.append(tok)
            continue
        # Strip punctuation for matching, reattach afterwards
        stripped = tok.strip(".,!?;:'\"()[]")
        prefix = tok[: len(tok) - len(tok.lstrip(".,!?;:'\"()[]"))]  # noqa: not needed
        suffix = tok[len(stripped) + len(tok) - len(tok.lstrip(".,!?;:'\"()[]")):]  # reattach
        # Simpler: just match stripped, keep original punctuation wrapper
        corrected_stripped = fuzzy_correct_token(stripped)
        if corrected_stripped != stripped:
            changed = True
        # Reconstruct with same case shape as original
        if stripped.isupper():
            corrected_stripped = corrected_stripped.upper()
        elif stripped[0].isupper() if stripped else False:
            corrected_stripped = corrected_stripped.capitalize()
        corrected.append(tok.replace(stripped, corrected_stripped, 1))
    return "".join(corrected) if changed else text


def augment_with_corrections(text: str) -> str:
    """
    Return original text + corrected version appended (space-separated).
    Slot extraction then sees both, maximising recall.
    """
    corrected = fuzzy_correct_text(text)
    if corrected == text:
        return text
    return f"{text} {corrected}"
