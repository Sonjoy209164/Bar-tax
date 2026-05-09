from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ORDERS_PATH = Path("data/orders/orders_store.jsonl")

ORDER_INTENT_PHRASES = (
    "order korte chai",
    "order dite chai",
    "order please",
    "book kore din",
    "book kore dao",
    "book korte chai",
    "eta nibo",
    "eta kinbo",
    "eta order",
    "checkout",
    "confirm order",
    "order confirm",
    "place order",
    "buy this",
    "i want to order",
    "i want to buy",
    "i'll take it",
    "i will take it",
    "add to cart",
    "cart e add",
    "eta cart e",
    "kinbo",
    "নিব",
    "নেব",
    "অর্ডার করতে চাই",
    "অর্ডার দিতে চাই",
    "বুক করুন",
    "কনফার্ম করুন",
)

CONFIRM_PHRASES = (
    "yes",
    "haa",
    "han",
    "ha",
    "হ্যাঁ",
    "হা",
    "হ্যা",
    "confirm",
    "confirmed",
    "ok",
    "okay",
    "done",
    "proceed",
    "agree",
    "sure",
)

CANCEL_PHRASES = (
    "no",
    "na",
    "না",
    "cancel",
    "cancel order",
    "cancel kore dao",
    "order cancel",
    "nevermind",
    "never mind",
    "not now",
)

PAYMENT_METHOD_PATTERNS = {
    "cod": ("cod", "cash on delivery", "cash", "ক্যাশ অন ডেলিভারি", "নগদ"),
    "bkash": ("bkash", "b kash", "bKash", "বিকাশ"),
    "nagad": ("nagad", "নগদ"),
    "rocket": ("rocket", "রকেট"),
    "card": ("card", "visa", "mastercard", "ক্রেডিট কার্ড", "ডেবিট কার্ড"),
}

_PHONE_PATTERN = re.compile(r"(?:01[3-9]\d{8}|\+8801[3-9]\d{8})")
_QUANTITY_PATTERN = re.compile(r"\b(\d+)\s*(?:ta|টা|টি|pcs|piece|pieces|nos?)?\b", re.IGNORECASE)


@dataclass
class OrderItem:
    product_id: str
    sku: str
    name: str
    quantity: int
    unit_price: float
    currency: str = "BDT"

    def line_total(self) -> float:
        return self.unit_price * self.quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "sku": self.sku,
            "name": self.name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "currency": self.currency,
            "line_total": self.line_total(),
        }


@dataclass
class OrderDraft:
    order_id: str = field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:6].upper()}")
    status: str = "draft"
    items: list[OrderItem] = field(default_factory=list)
    customer_name: str | None = None
    customer_phone: str | None = None
    delivery_area: str | None = None
    payment_method: str | None = None
    notes: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confirmed_at: str | None = None

    def subtotal(self) -> float:
        return sum(item.line_total() for item in self.items)

    def delivery_charge(self) -> int:
        inside_dhaka_areas = {
            "dhanmondi", "gulshan", "banani", "uttara", "mirpur", "mohakhali",
            "lalbagh", "old dhaka", "motijheel", "tejgaon", "bashundhara",
            "baridhara", "khilgaon", "shyamoli", "mohammadpur", "jatrabari",
            "demra", "rampura", "badda", "pallabi", "savar", "gazipur",
            "azimpur", "rayer bazar", "dhaka",
        }
        if self.delivery_area and self.delivery_area.strip().casefold() in inside_dhaka_areas:
            sub = self.subtotal()
            return 0 if sub >= 5000 else 80
        return 150

    def grand_total(self) -> float:
        return self.subtotal() + self.delivery_charge()

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.items:
            missing.append("product")
        if not self.customer_name:
            missing.append("name")
        if not self.customer_phone:
            missing.append("phone")
        if not self.delivery_area:
            missing.append("delivery area")
        if not self.payment_method:
            missing.append("payment method")
        return missing

    def is_ready_to_confirm(self) -> bool:
        return not self.missing_fields()

    def summary_text(self) -> str:
        lines: list[str] = ["Order Summary:"]
        for item in self.items:
            lines.append(f"  {item.name} x{item.quantity} — BDT {item.line_total():,.0f}")
        lines.append(f"Subtotal: BDT {self.subtotal():,.0f}")
        dc = self.delivery_charge()
        lines.append(f"Delivery: BDT {dc}")
        lines.append(f"Grand Total: BDT {self.grand_total():,.0f}")
        if self.customer_name:
            lines.append(f"Name: {self.customer_name}")
        if self.customer_phone:
            lines.append(f"Phone: {self.customer_phone}")
        if self.delivery_area:
            lines.append(f"Delivery Area: {self.delivery_area}")
        if self.payment_method:
            lines.append(f"Payment: {self.payment_method.upper()}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "delivery_area": self.delivery_area,
            "payment_method": self.payment_method,
            "notes": self.notes,
            "subtotal": self.subtotal(),
            "delivery_charge": self.delivery_charge(),
            "grand_total": self.grand_total(),
            "created_at": self.created_at,
            "confirmed_at": self.confirmed_at,
        }


class OrderWorkflowEngine:
    """Session-scoped order workflow engine. One instance per chat session."""

    def __init__(self) -> None:
        self._draft: OrderDraft | None = None
        self._awaiting_confirmation: bool = False

    @property
    def has_active_draft(self) -> bool:
        return self._draft is not None

    @property
    def awaiting_confirmation(self) -> bool:
        return self._awaiting_confirmation

    def is_order_intent(self, text: str) -> bool:
        normalized = text.casefold().strip()
        return any(phrase in normalized for phrase in ORDER_INTENT_PHRASES)

    def is_confirm(self, text: str) -> bool:
        normalized = text.casefold().strip()
        return any(normalized == phrase or normalized.startswith(phrase) for phrase in CONFIRM_PHRASES)

    def is_cancel(self, text: str) -> bool:
        normalized = text.casefold().strip()
        return any(phrase in normalized for phrase in CANCEL_PHRASES)

    def start_draft(
        self,
        product_id: str,
        sku: str,
        name: str,
        unit_price: float,
        quantity: int = 1,
        currency: str = "BDT",
    ) -> OrderDraft:
        self._draft = OrderDraft(
            items=[OrderItem(product_id=product_id, sku=sku, name=name, quantity=quantity, unit_price=unit_price, currency=currency)]
        )
        self._awaiting_confirmation = False
        return self._draft

    def add_item(self, product_id: str, sku: str, name: str, unit_price: float, quantity: int = 1, currency: str = "BDT") -> None:
        if self._draft is None:
            self._draft = OrderDraft()
        for existing in self._draft.items:
            if existing.product_id == product_id:
                existing.quantity += quantity
                return
        self._draft.items.append(OrderItem(product_id=product_id, sku=sku, name=name, quantity=quantity, unit_price=unit_price, currency=currency))

    def update_from_text(self, text: str) -> None:
        if self._draft is None:
            return
        phone_match = _PHONE_PATTERN.search(text)
        if phone_match and not self._draft.customer_phone:
            self._draft.customer_phone = phone_match.group()

        normalized = text.casefold()
        for method, patterns in PAYMENT_METHOD_PATTERNS.items():
            if any(p in normalized for p in patterns):
                self._draft.payment_method = method
                break

        quantity_match = _QUANTITY_PATTERN.search(text)
        if quantity_match and self._draft.items:
            qty = int(quantity_match.group(1))
            if 1 <= qty <= 100:
                self._draft.items[0].quantity = qty

        known_areas = [
            "dhanmondi", "gulshan", "banani", "uttara", "mirpur", "mohakhali",
            "lalbagh", "motijheel", "tejgaon", "bashundhara", "khilgaon",
            "shyamoli", "mohammadpur", "jatrabari", "rampura", "badda",
            "dhaka", "chittagong", "ctg", "sylhet", "rajshahi", "khulna",
            "comilla", "mymensingh", "narayanganj", "gazipur", "savar",
        ]
        for area in known_areas:
            if area in normalized:
                self._draft.delivery_area = area.title()
                break

        words = text.split()
        if not self._draft.customer_name and len(words) >= 1:
            candidate = " ".join(w for w in words[:3] if re.match(r"^[A-Za-zঀ-৿]{2,}$", w))
            if candidate and not phone_match:
                self._draft.customer_name = candidate

    def build_ask_for_missing(self) -> str:
        if self._draft is None:
            return "Please tell me which product you'd like to order."
        missing = self._draft.missing_fields()
        if not missing:
            return ""
        field_prompts = {
            "product": "Which product would you like to order?",
            "name": "your name",
            "phone": "your phone number",
            "delivery area": "your delivery area",
            "payment method": "payment method (COD / bKash / Nagad / card)",
        }
        parts = [field_prompts.get(f, f) for f in missing]
        return "Please provide: " + ", ".join(parts) + "."

    def prepare_confirmation(self) -> tuple[str, bool]:
        if self._draft is None:
            return "No active order draft.", False
        missing = self._draft.missing_fields()
        if missing:
            return self.build_ask_for_missing(), False
        self._awaiting_confirmation = True
        return (
            self._draft.summary_text()
            + "\n\nShould I confirm this order? (yes / no)",
            True,
        )

    def confirm(self) -> tuple[str, OrderDraft | None]:
        if self._draft is None:
            return "No active order draft to confirm.", None
        self._draft.status = "confirmed"
        self._draft.confirmed_at = datetime.now(timezone.utc).isoformat()
        _persist_order(self._draft)
        confirmed = self._draft
        self._draft = None
        self._awaiting_confirmation = False
        return (
            f"Order confirmed! Your order ID is **{confirmed.order_id}**.\n"
            f"Grand Total: BDT {confirmed.grand_total():,.0f}.\n"
            f"We will contact you at {confirmed.customer_phone} to arrange delivery.",
            confirmed,
        )

    def cancel(self) -> str:
        self._draft = None
        self._awaiting_confirmation = False
        return "Order cancelled. Let me know if you want to browse more products."

    def get_draft(self) -> OrderDraft | None:
        return self._draft


def _persist_order(order: OrderDraft) -> None:
    _ORDERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _ORDERS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(order.to_dict(), ensure_ascii=False))
        handle.write("\n")


def load_order(order_id: str) -> OrderDraft | None:
    if not _ORDERS_PATH.exists():
        return None
    with _ORDERS_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("order_id") == order_id:
                    draft = OrderDraft(order_id=data["order_id"])
                    draft.status = data.get("status", "confirmed")
                    draft.customer_name = data.get("customer_name")
                    draft.customer_phone = data.get("customer_phone")
                    draft.delivery_area = data.get("delivery_area")
                    draft.payment_method = data.get("payment_method")
                    draft.notes = data.get("notes")
                    draft.created_at = data.get("created_at", draft.created_at)
                    draft.confirmed_at = data.get("confirmed_at")
                    for item_data in data.get("items", []):
                        draft.items.append(
                            OrderItem(
                                product_id=item_data["product_id"],
                                sku=item_data["sku"],
                                name=item_data["name"],
                                quantity=item_data["quantity"],
                                unit_price=item_data["unit_price"],
                                currency=item_data.get("currency", "BDT"),
                            )
                        )
                    return draft
            except (json.JSONDecodeError, KeyError):
                continue
    return None
