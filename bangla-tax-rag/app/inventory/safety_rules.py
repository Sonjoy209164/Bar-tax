"""
Layer 1 of the conversation entry point: deterministic safety rules.

This module owns ONLY the boundary types where a regex/keyword match is the
right tool because the cost of a false negative is high:

  - self_harm_or_crisis
  - abusive_severe
  - abusive_mild
  - medical_or_health_advice
  - legal_advice
  - political
  - random_tech                  (refusal — keeps the bot from drifting into a general chatbot)
  - order_tracking_support       (needs deterministic slot ask)
  - payment_support              (needs deterministic slot ask)

Everything else (chitchat, romantic, impression, emotional, gift, occasion,
vague shopping, personal_question_about_bot) is handled by the LLM classifier
in boundary_classifier.py, with a slim keyword fallback for offline mode.

This file is the only place new regex keyword tuples are allowed to live.
"""
from __future__ import annotations

import re
from typing import Any

from app.inventory.boundary_text import has_any, normalize

SELF_HARM_KEYWORDS: tuple[str, ...] = (
    "kill myself",
    "suicide",
    "self harm",
    "do not want to live",
    "don't want to live",
    "dont want to live",
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

SEVERE_ABUSIVE_KEYWORDS: tuple[str, ...] = (
    "i will kill",
    "kill you",
    "marbo",
    "mere felbo",
    "threat",
    "hate speech",
    "মারবো",
    "মেরে ফেলব",
)

MILD_ABUSIVE_KEYWORDS: tuple[str, ...] = (
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

POLITICAL_KEYWORDS: tuple[str, ...] = (
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

MEDICAL_ADVICE_KEYWORDS: tuple[str, ...] = (
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

LEGAL_ADVICE_KEYWORDS: tuple[str, ...] = (
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

RANDOM_TECH_KEYWORDS: tuple[str, ...] = (
    "python code",
    "javascript",
    "java code",
    "sql query",
    "ram kivabe kaj kore",
    "processor kivabe kaj kore",
    "write code",
    "build a website",
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

PAYMENT_SUPPORT_KEYWORDS: tuple[str, ...] = (
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
    "pay by card",
    "pay with card",
    "ক্যাশ অন ডেলিভারি",
    "বিকাশ",
    "নগদ",
    "রকেট",
    "কার্ড পেমেন্ট",
    "পেমেন্ট",
)

ORDER_TRACKING_KEYWORDS: tuple[str, ...] = (
    "order track",
    "track order",
    "track my order",
    "order status",
    "where is my parcel",
    "amar order track",
    "amar order kothay",
    "parcel kothay",
    "delivery status",
    "অর্ডার ট্র্যাক",
    "অর্ডার কোথায়",
    "পার্সেল কোথায়",
    "ডেলিভারি স্ট্যাটাস",
)


SafetyMatch = dict[str, Any]


def match_safety(normalized_text: str) -> SafetyMatch | None:
    """Return a structured match for the first applicable safety rule, else None.

    Safety rules are ordered by severity: a self-harm signal must short-circuit
    every other branch, even if other keywords also fire in the same message.
    """
    if has_any(normalized_text, SELF_HARM_KEYWORDS):
        return _match(
            boundary_type="self_harm_or_crisis",
            risk_level="critical",
            allowed_action="crisis_safe_response",
            handoff_recommended=True,
            confidence=0.96,
            reasoning="Detected crisis/self-harm language; commerce redirect is disabled.",
            no_followup=True,
            no_categories=True,
        )

    if has_any(normalized_text, SEVERE_ABUSIVE_KEYWORDS):
        return _match(
            boundary_type="abusive_severe",
            risk_level="high",
            allowed_action="stop_or_handoff",
            handoff_recommended=True,
            confidence=0.92,
            reasoning="Detected severe abusive or threatening wording.",
            no_categories=True,
        )

    if has_any(normalized_text, MILD_ABUSIVE_KEYWORDS):
        return _match(
            boundary_type="abusive_mild",
            risk_level="medium",
            allowed_action="deescalate",
            confidence=0.86,
            reasoning="Detected mild abuse; de-escalating before continuing.",
            no_categories=True,
        )

    # Order/payment support intents are deterministic — they need the exact
    # slot ask ("share the order ID"). LLM rewording would dilute the action.
    if has_any(normalized_text, ORDER_TRACKING_KEYWORDS):
        return _match(
            boundary_type="order_tracking_support",
            risk_level="low",
            allowed_action="store_support_redirect",
            confidence=0.88,
            reasoning="Detected order tracking request; asking for order ID or phone.",
            slots={"support_topic": "order_tracking"},
        )

    if has_any(normalized_text, PAYMENT_SUPPORT_KEYWORDS):
        return _match(
            boundary_type="payment_support",
            risk_level="low",
            allowed_action="store_support_redirect",
            confidence=0.86,
            reasoning="Detected payment support request; redirecting to payment help.",
            slots={"support_topic": "payment"},
        )

    if has_any(normalized_text, POLITICAL_KEYWORDS):
        return _match(
            boundary_type="political",
            risk_level="medium",
            allowed_action="safe_refusal_redirect",
            confidence=0.88,
            reasoning="Detected political topic; keeping the brand neutral.",
            no_categories=True,
        )

    if has_any(normalized_text, MEDICAL_ADVICE_KEYWORDS):
        return _match(
            boundary_type="medical_or_health_advice",
            risk_level="high",
            allowed_action="safe_refusal_redirect",
            handoff_recommended=True,
            confidence=0.88,
            reasoning="Detected medical advice request; avoiding diagnosis or treatment.",
            recommended_categories=("wellness", "self-care"),
        )

    if has_any(normalized_text, LEGAL_ADVICE_KEYWORDS):
        return _match(
            boundary_type="legal_advice",
            risk_level="high",
            allowed_action="safe_refusal_redirect",
            handoff_recommended=True,
            confidence=0.88,
            reasoning="Detected legal advice request; avoiding legal guidance.",
            no_categories=True,
        )

    if has_any(normalized_text, RANDOM_TECH_KEYWORDS):
        return _match(
            boundary_type="random_tech",
            risk_level="low",
            allowed_action="safe_refusal_redirect",
            confidence=0.78,
            reasoning="Detected non-catalog technical request; redirecting to store support.",
            no_categories=True,
        )

    return None


def _match(
    *,
    boundary_type: str,
    risk_level: str,
    allowed_action: str,
    confidence: float,
    reasoning: str,
    handoff_recommended: bool = False,
    no_followup: bool = False,
    no_categories: bool = False,
    slots: dict[str, Any] | None = None,
    recommended_categories: tuple[str, ...] = (),
) -> SafetyMatch:
    return {
        "boundary_type": boundary_type,
        "risk_level": risk_level,
        "allowed_action": allowed_action,
        "confidence": confidence,
        "reasoning": reasoning,
        "handoff_recommended": handoff_recommended,
        "no_followup": no_followup,
        "no_categories": no_categories,
        "slots": dict(slots or {}),
        "recommended_categories": recommended_categories if not no_categories else (),
    }


__all__ = ["match_safety", "SafetyMatch"]
