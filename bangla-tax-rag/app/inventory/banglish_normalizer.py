"""
Banglish → Bangla phonetic normalization.

Converts common romanized Bengali spellings to their Bangla equivalents so
that downstream slot extraction sees consistent tokens regardless of whether
the customer typed "sharee", "saree", or "শাড়ি".

Design: rule table + simple regex replace.  Fast, deterministic, no external
deps.  The LLM slot extractor (Ollama) handles harder ambiguities when available.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Token-level substitution table — order matters (longer patterns first).
# Keys are regex patterns; values are the Bangla replacement.
# ---------------------------------------------------------------------------
_RULES: list[tuple[str, str]] = [
    # Categories
    (r"\bsharee\b|\bshari\b|\bsaree\b|\bsari\b",                     "শাড়ি"),
    (r"\bpanjabi\b|\bpunjabi\b|\bpanjab\b",                           "পাঞ্জাবি"),
    (r"\bkurti\b|\bkurtee\b",                                          "কুর্তি"),
    (r"\bsalwar\b|\bshalwar\b|\bshalwaar\b",                          "সালোয়ার"),
    (r"\blehenga\b|\blehnga\b",                                        "লেহেঙ্গা"),
    (r"\bblouse\b",                                                    "ব্লাউজ"),
    (r"\bjewelry\b|\bjewellery\b|\bgahna\b|\babhushon\b",             "গহনা"),
    (r"\bchuri\b|\bbangles\b|\bbangle\b",                             "চুড়ি"),
    # Fabrics
    (r"\bjamdani\b|\bjaamdaani\b",                                    "জামদানি"),
    (r"\bkatan\b|\bkatan\b|\bcotton\b",                               "কটন"),
    (r"\bmuslin\b|\bmusleen\b",                                       "মসলিন"),
    (r"\bsilk\b|\bsilken\b|\breshom\b",                               "সিল্ক"),
    (r"\bgeorgette\b",                                                "জর্জেট"),
    (r"\bchiffon\b|\bshifon\b",                                       "শিফন"),
    # Colors
    (r"\blaal\b|\blal\b",                                             "লাল"),
    (r"\bneel\b|\bnil\b|\bneela\b",                                   "নীল"),
    (r"\bshabuj\b|\bsabuj\b|\bgreen\b",                              "সবুজ"),
    (r"\bkalo\b|\bkala\b|\bblack\b",                                  "কালো"),
    (r"\bsada\b|\bshada\b|\bwhite\b",                                 "সাদা"),
    (r"\bholud\b|\bylellow\b|\byellow\b",                             "হলুদ"),
    (r"\bkhaki\b",                                                    "খাকি"),
    # Occasions
    (r"\beid\b|\beid ul fitr\b|\beid ul adha\b",                     "ঈদ"),
    (r"\bboishakh\b|\bbaishakh\b|\bpohela boishakh\b",               "বৈশাখ"),
    (r"\bwedding\b|\bbiye\b|\bbiyebarir\b",                          "বিবাহ"),
    (r"\bpuja\b|\bdurga puja\b",                                     "পূজা"),
    # Common intent words
    (r"\bache\b|\basa\b|\bache ki\b",                                "আছে"),
    (r"\bdekao\b|\bdekhao\b|\bdekhte chai\b|\bdekhte chai\b",       "দেখাও"),
    (r"\bkoto\b|\bkoto taka\b",                                      "কত"),
    (r"\bkinte chai\b|\bkinbo\b|\bkinbe\b",                          "কিনতে চাই"),
    (r"\blagbe\b|\bdorkar\b",                                        "লাগবে"),
    (r"\bvalo\b|\bbhalo\b",                                          "ভালো"),
    (r"\bnibo\b|\bnebo\b",                                           "নিব"),
    (r"\bkonta\b|\bkontar\b",                                        "কোনটা"),
    (r"\baache\b",                                                   "আছে"),
]

_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in _RULES
]


def normalize_banglish(text: str) -> str:
    """
    Replace romanized Bangla tokens with their Unicode equivalents.
    Returns the original text if no substitutions are made.
    Non-destructive: the original is still searchable — this is additive.
    """
    result = text
    for pattern, replacement in _COMPILED:
        result = pattern.sub(replacement, result)
    return result


def augment_with_bangla(text: str) -> str:
    """
    Return the original text PLUS any Bangla translations appended.
    Slot extraction then sees both romanized and Bangla forms, maximizing recall.
    """
    translated = normalize_banglish(text)
    if translated == text:
        return text
    return f"{text} {translated}"
