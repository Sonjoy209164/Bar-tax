from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


_POLICY_PATH = Path("data/inventory/policies.json")

POLICY_QUESTION_PHRASES = (
    "delivery charge",
    "delivery koto",
    "delivery fee",
    "delivery cost",
    "ডেলিভারি চার্জ",
    "ডেলিভারি কত",
    "delivery eta",
    "delivery time",
    "koto din lage",
    "কত দিন লাগে",
    "কতদিন লাগে",
    "payment method",
    "payment option",
    "bkash payment",
    "cod available",
    "nagad",
    "rocket payment",
    "refund",
    "রিফান্ড",
    "ফেরত দিতে",
    "exchange",
    "return policy",
    "ভুল product",
    "ভুল প্রোডাক্ট",
    "damaged product",
    "wrong product",
    "wrong item",
    "cancel order",
    "order cancel",
    "alteration",
    "stitching",
    "size exchange",
    "exchange policy",
    "card payment",
    "advance payment",
    "contact",
    "phone number",
    "shop hours",
)


@lru_cache(maxsize=1)
def load_policies() -> dict[str, Any]:
    if not _POLICY_PATH.exists():
        return {}
    return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))


def is_policy_question(text: str) -> bool:
    normalized = text.casefold()
    return any(phrase in normalized for phrase in POLICY_QUESTION_PHRASES)


class PolicyQAEngine:
    """Answers delivery/payment/refund/exchange questions strictly from policies.json."""

    def __init__(self) -> None:
        self._policies = load_policies()

    def answer(self, question: str) -> str | None:
        if not self._policies:
            return None
        normalized = question.casefold()

        if self._matches(normalized, ("delivery time", "koto din", "din lage", "কতদিন", "কত দিন", "eta")):
            return self._delivery_time_answer(normalized)

        if self._matches(normalized, ("delivery charge", "delivery koto", "delivery fee", "ডেলিভারি চার্জ", "ডেলিভারি কত")):
            return self._delivery_charge_answer(normalized)

        if self._matches(normalized, ("payment", "bkash", "nagad", "cod", "rocket", "card", "পেমেন্ট", "বিকাশ")):
            return self._payment_answer(normalized)

        if self._matches(normalized, ("refund", "রিফান্ড", "ফেরত", "money back")):
            return self._refund_answer()

        if self._matches(normalized, ("exchange", "return policy", "size exchange", "ভুল সাইজ", "wrong size", "ভুল প্রোডাক্ট", "wrong product", "damaged")):
            return self._exchange_answer(normalized)

        if self._matches(normalized, ("alteration", "stitching", "সেলাই", "আলতারেশন")):
            return self._alteration_answer()

        if self._matches(normalized, ("contact", "phone", "ফোন", "whatsapp", "hours", "সময়")):
            return self._contact_answer()

        return None

    def _delivery_charge_answer(self, normalized: str) -> str:
        delivery = self._policies.get("delivery", {})
        inside = delivery.get("inside_dhaka", {})
        outside = delivery.get("outside_dhaka", {})
        free_threshold = delivery.get("free_delivery_threshold", {})

        parts: list[str] = []
        if self._matches(normalized, ("outside", "বাইরে", "district", "bahra")):
            parts.append(f"Outside Dhaka: BDT {outside.get('charge', 150)} delivery charge.")
        elif self._matches(normalized, ("dhaka", "ঢাকা", "inside")):
            parts.append(f"Inside Dhaka: BDT {inside.get('charge', 80)} delivery charge.")
        else:
            parts.append(f"Inside Dhaka: BDT {inside.get('charge', 80)}.")
            parts.append(f"Outside Dhaka: BDT {outside.get('charge', 150)}.")

        if free_threshold:
            parts.append(
                f"Orders above BDT {free_threshold.get('amount', 5000):,} get free delivery inside Dhaka."
            )
        return " ".join(parts)

    def _delivery_time_answer(self, normalized: str) -> str:
        delivery = self._policies.get("delivery", {})
        inside = delivery.get("inside_dhaka", {})
        outside = delivery.get("outside_dhaka", {})
        express = delivery.get("express_dhaka", {})

        if self._matches(normalized, ("outside", "বাইরে", "district")):
            return f"Outside Dhaka delivery takes {outside.get('eta', '3-5 working days')} via courier."
        if self._matches(normalized, ("express", "same day", "আজকে")):
            if express.get("available"):
                return f"Express delivery inside Dhaka: {express.get('eta', 'Same day')} — BDT {express.get('charge', 150)} extra."
        return f"Inside Dhaka delivery takes {inside.get('eta', '1-2 working days')}. Outside Dhaka: {outside.get('eta', '3-5 working days')}."

    def _payment_answer(self, normalized: str) -> str:
        payment = self._policies.get("payment", {})
        methods = payment.get("methods", [])
        cod = payment.get("cod", {})

        if self._matches(normalized, ("bkash", "বিকাশ")):
            bkash = payment.get("bkash", {})
            if bkash.get("available"):
                return f"Yes, bKash payment is available. {bkash.get('instruction', '')}"
            return "bKash payment is not currently available."

        if self._matches(normalized, ("nagad", "নগদ")):
            nagad = payment.get("nagad", {})
            if nagad.get("available"):
                return f"Yes, Nagad payment is available. {nagad.get('instruction', '')}"
            return "Nagad payment is not currently available."

        if self._matches(normalized, ("cod", "cash on delivery", "cash", "ক্যাশ")):
            if cod.get("available"):
                return f"Yes, COD is available up to BDT {cod.get('limit_bdt', 10000):,}. {cod.get('note', '')}"
            return "COD is not currently available."

        if self._matches(normalized, ("card", "visa", "mastercard")):
            card = payment.get("card", {})
            if card.get("available"):
                return f"Card payment (Visa/Mastercard) is available. {card.get('note', '')}"
            return "Card payment is not currently available."

        method_str = ", ".join(methods)
        return f"We accept: {method_str}. COD available up to BDT {cod.get('limit_bdt', 10000):,}."

    def _refund_answer(self) -> str:
        refund = self._policies.get("refund", {})
        msg = refund.get("message", "")
        exceptions = refund.get("exceptions", [])
        not_eligible = refund.get("not_eligible", [])

        lines: list[str] = [msg or "Refund policy:"]
        if exceptions:
            lines.append(f"Eligible cases: {'; '.join(exceptions)}.")
        if not_eligible:
            lines.append(f"Not eligible: {'; '.join(not_eligible[:2])}.")
        return " ".join(lines)

    def _exchange_answer(self, normalized: str) -> str:
        exchange = self._policies.get("exchange", {})
        damaged = self._policies.get("damaged_product", {})

        if self._matches(normalized, ("damaged", "ক্ষতিগ্রস্ত", "ভুল প্রোডাক্ট", "wrong product", "wrong item")):
            return damaged.get("policy", "Contact us within 24 hours with photo proof for damaged products.")

        days = exchange.get("allowed_days", 3)
        conditions = exchange.get("conditions", [])
        cond_str = "; ".join(conditions[:3]) if conditions else ""
        return (
            f"Exchange is allowed within {days} days. Conditions: {cond_str}. "
            "Contact us to initiate exchange."
        )

    def _alteration_answer(self) -> str:
        alteration = self._policies.get("alteration", {})
        if not alteration.get("available"):
            return "Alteration service is not currently available."
        products = alteration.get("products", [])
        lead = alteration.get("lead_time", "3-5 working days")
        return (
            f"Alteration is available for: {', '.join(products)}. "
            f"Lead time: {lead}. {alteration.get('cost', '')}"
        )

    def _contact_answer(self) -> str:
        contact = self._policies.get("contact", {})
        phone = contact.get("phone", "N/A")
        hours = contact.get("hours", "N/A")
        return f"Contact us at {phone} (WhatsApp also available). Hours: {hours}."

    @staticmethod
    def _matches(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)
