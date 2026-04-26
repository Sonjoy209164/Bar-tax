from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.schemas import InventorySearchFilters
from app.inventory.ontology import ProductOntology, normalize_inventory_text


@dataclass(frozen=True)
class InventoryIntentResult:
    intent: str
    confidence: float
    reasons: tuple[str, ...] = ()


class InventoryIntentClassifier:
    SMALL_TALK = (
        "hello",
        "hi",
        "hey",
        "how are you",
        "how are you doing",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
        "who are you",
        "what can you do",
    )
    EXACT_LOOKUP = (
        "do you have",
        "have any",
        "got any",
        "is there",
        "show me",
        "find me",
        "looking for",
        "i need",
    )
    RECOMMENDATION = ("recommend", "suggest", "best", "what should i buy", "what should i sell")
    COMPARISON = ("compare", "vs", "versus", "difference between", "which is better")
    PRICE_OBJECTION = ("too expensive", "too pricey", "cheaper", "lower price", "over budget", "price is high")
    AVAILABILITY_OBJECTION = ("out of stock", "not available", "unavailable", "need it now", "need an in stock")
    QUALITY_OBJECTION = ("better option", "something better", "more premium", "higher end", "better quality")
    CROSS_SELL = ("bundle", "add on", "add-on", "accessory", "pair with", "go with", "complete setup", "cross sell")
    RESTOCK = ("restock", "reorder", "low stock", "running low", "below threshold", "stockout")
    BUSINESS_ANALYSIS = (
        "sales",
        "revenue",
        "margin",
        "profit",
        "trend",
        "forecast",
        "demand",
        "supplier",
        "returns",
        "why",
    )
    DETAIL = ("tell me about", "details on", "detail on", "more about", "what about")
    INVENTORY_HINTS = (
        "product",
        "products",
        "item",
        "items",
        "inventory",
        "stock",
        "price",
        "pricing",
        "category",
        "brand",
        "customer",
    )

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()

    def classify(self, question: str, *, filters: InventorySearchFilters | None = None) -> InventoryIntentResult:
        text = normalize_inventory_text(question)
        filters = filters or InventorySearchFilters()
        reasons: list[str] = []
        product_type = self.ontology.detect_product_type(text=question)
        has_inventory_hint = product_type is not None or self._has_any(text, self.INVENTORY_HINTS)

        if self._is_small_talk(text, has_inventory_hint=has_inventory_hint):
            return InventoryIntentResult("small_talk", 0.96, ("Conversational phrase without inventory constraints.",))

        if self._has_any(text, self.PRICE_OBJECTION):
            return InventoryIntentResult("price_objection", 0.93, ("Detected price objection language.",))

        if self._has_any(text, self.AVAILABILITY_OBJECTION):
            return InventoryIntentResult("availability_objection", 0.91, ("Detected availability objection language.",))

        if self._has_any(text, self.QUALITY_OBJECTION):
            return InventoryIntentResult("quality_objection", 0.88, ("Detected quality or step-up objection language.",))

        if self._has_any(text, self.CROSS_SELL):
            return InventoryIntentResult("cross_sell", 0.9, ("Detected bundle, add-on, or cross-sell language.",))

        if self._has_any(text, self.COMPARISON):
            return InventoryIntentResult("comparison", 0.9, ("Detected comparison language.",))

        if self._has_any(text, self.RESTOCK):
            return InventoryIntentResult("restock", 0.88, ("Detected stock urgency or restock language.",))

        if self._looks_like_business_analysis(text):
            return InventoryIntentResult("business_analysis", 0.78, ("Detected operational analysis terms.",))

        if filters.product_ids or self._has_any(text, self.DETAIL) or self._has_sku_like_token(question):
            return InventoryIntentResult("product_detail", 0.88, ("Detected focused product detail reference.",))

        if self._has_any(text, self.RECOMMENDATION):
            confidence = 0.9 if product_type else 0.76
            reasons.append("Detected recommendation language.")
            if product_type:
                reasons.append(f"Detected product type: {product_type}.")
            return InventoryIntentResult("recommendation", confidence, tuple(reasons))

        if self._has_any(text, self.EXACT_LOOKUP):
            confidence = 0.86 if product_type else 0.72
            reasons.append("Detected direct lookup/search language.")
            if product_type:
                reasons.append(f"Detected product type: {product_type}.")
                return InventoryIntentResult("product_search", confidence, tuple(reasons))
            return InventoryIntentResult("exact_lookup", confidence, tuple(reasons))

        if has_inventory_hint:
            return InventoryIntentResult("product_search", 0.68, ("Detected product or inventory terms.",))

        return InventoryIntentResult("unknown", 0.35, ("No strong ecommerce intent detected.",))

    def _looks_like_business_analysis(self, text: str) -> bool:
        if not self._has_any(text, self.BUSINESS_ANALYSIS):
            return False
        analysis_terms = ("why", "trend", "forecast", "demand", "drop", "increase", "month", "quarter", "margin")
        return self._has_any(text, analysis_terms)

    def _is_small_talk(self, text: str, *, has_inventory_hint: bool) -> bool:
        if has_inventory_hint:
            return False
        token_count = len(text.split())
        return token_count <= 10 and self._has_any(text, self.SMALL_TALK)

    @staticmethod
    def _has_sku_like_token(text: str) -> bool:
        return bool(re.search(r"\b[A-Za-z]{2,}(?:-[A-Za-z0-9]+)+\b", text))

    @staticmethod
    def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
        for phrase in phrases:
            if " " in phrase:
                if phrase in text:
                    return True
                continue
            if re.search(rf"\b{re.escape(phrase)}\b", text):
                return True
        return False
