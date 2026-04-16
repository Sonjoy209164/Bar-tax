from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.schemas import InventorySearchFilters
from app.inventory.ontology import ProductOntology, normalize_inventory_text


@dataclass(frozen=True)
class InventoryPreferenceProfile:
    product_type: str | None = None
    product_family: str | None = None
    category: str | None = None
    brand: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    quality_level: str | None = None
    needs_in_stock: bool = False
    use_cases: tuple[str, ...] = ()
    feature_requirements: tuple[str, ...] = ()
    avoid_product_types: tuple[str, ...] = ()
    selected_product_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_plan_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in (
            "product_type",
            "product_family",
            "category",
            "brand",
            "budget_min",
            "budget_max",
            "quality_level",
            "needs_in_stock",
            "use_cases",
            "feature_requirements",
            "avoid_product_types",
            "selected_product_ids",
            "confidence",
            "evidence",
        ):
            value = getattr(self, key)
            if value is None:
                continue
            if isinstance(value, tuple):
                if value:
                    payload[key] = list(value)
                continue
            if isinstance(value, bool):
                if value:
                    payload[key] = value
                continue
            if value != "":
                payload[key] = value
        return payload


class InventoryPreferenceExtractor:
    RANGE_PATTERN = re.compile(
        r"(?:between|from)\s*\$?\s*(\d+(?:\.\d+)?)\s*(?:and|to|-)\s*\$?\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    MAX_PRICE_PATTERN = re.compile(
        r"(?:under|below|less than|up to|within|max|maximum)\s*\$?\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    MIN_PRICE_PATTERN = re.compile(
        r"(?:over|above|more than|at least|min|minimum)\s*\$?\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    FEATURE_KEYWORDS: dict[str, tuple[str, ...]] = {
        "wireless": ("wireless", "bluetooth"),
        "noise_cancellation": ("noise cancellation", "noise cancelling", "anc"),
        "usb_c": ("usb c", "usb-c"),
        "battery_life": ("battery", "battery life", "hours"),
        "ergonomic": ("ergonomic", "lumbar"),
        "gps": ("gps",),
        "heart_rate": ("heart rate", "heart-rate"),
        "portable": ("portable", "travel"),
        "premium": ("premium", "flagship", "high end", "high-end"),
    }
    USE_CASE_KEYWORDS: dict[str, tuple[str, ...]] = {
        "office_calls": ("office call", "office calls", "meeting", "meetings", "calls", "webinar"),
        "gaming": ("gaming", "game"),
        "travel": ("travel", "commute", "commuter"),
        "fitness": ("fitness", "workout", "running", "health"),
        "podcasting": ("podcast", "podcasting", "recording", "webinar"),
        "business": ("business", "manager", "analyst", "client"),
        "editing": ("editing", "studio", "content"),
    }
    PREMIUM_HINTS = ("premium", "best", "top", "flagship", "high end", "high-end", "luxury", "pro")
    BUDGET_HINTS = ("budget", "affordable", "value", "cheap", "cheapest", "lower price", "low price")
    AVAILABILITY_HINTS = ("in stock", "available now", "ready to sell", "available", "sellable now")

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()

    def extract(
        self,
        question: str,
        *,
        filters: InventorySearchFilters | None = None,
        products: list[object] | None = None,
    ) -> InventoryPreferenceProfile:
        filters = filters or InventorySearchFilters()
        products = products or []
        text = normalize_inventory_text(question)
        evidence: list[str] = []

        product_type = self.ontology.detect_product_type(text=question)
        if product_type:
            evidence.append(f"product_type:{product_type}")
        product_family = self.ontology.product_family(product_type)

        category = filters.categories[0] if filters.categories else self.ontology.category_for_product_type(product_type)
        if category:
            evidence.append(f"category:{category}")

        brand = self._extract_brand(text=text, filters=filters, products=products)
        if brand:
            evidence.append(f"brand:{brand}")

        budget_min, budget_max = self._extract_budget(question, filters=filters)
        if budget_min is not None:
            evidence.append(f"budget_min:{budget_min}")
        if budget_max is not None:
            evidence.append(f"budget_max:{budget_max}")

        quality_level = self._extract_quality_level(text)
        if quality_level:
            evidence.append(f"quality:{quality_level}")

        needs_in_stock = bool(filters.min_stock and filters.min_stock > 0) or self._has_any(text, self.AVAILABILITY_HINTS)
        if needs_in_stock:
            evidence.append("needs_in_stock:true")

        feature_requirements = tuple(self._extract_keyword_matches(text, self.FEATURE_KEYWORDS))
        use_cases = tuple(self._extract_keyword_matches(text, self.USE_CASE_KEYWORDS))
        avoid_product_types = tuple(self._extract_avoid_product_types(text))
        selected_product_ids = tuple(filters.product_ids)

        confidence = self._estimate_confidence(
            product_type=product_type,
            category=category,
            brand=brand,
            budget_min=budget_min,
            budget_max=budget_max,
            quality_level=quality_level,
            feature_requirements=feature_requirements,
            use_cases=use_cases,
            selected_product_ids=selected_product_ids,
        )

        return InventoryPreferenceProfile(
            product_type=product_type,
            product_family=product_family,
            category=category,
            brand=brand,
            budget_min=budget_min,
            budget_max=budget_max,
            quality_level=quality_level,
            needs_in_stock=needs_in_stock,
            use_cases=use_cases,
            feature_requirements=feature_requirements,
            avoid_product_types=avoid_product_types,
            selected_product_ids=selected_product_ids,
            confidence=confidence,
            evidence=tuple(evidence),
        )

    def _extract_brand(
        self,
        *,
        text: str,
        filters: InventorySearchFilters,
        products: list[object],
    ) -> str | None:
        if filters.brands:
            return filters.brands[0]
        seen: set[str] = set()
        for product in products:
            brand = getattr(product, "brand", None)
            if not isinstance(brand, str) or not brand.strip():
                continue
            brand_key = normalize_inventory_text(brand)
            if not brand_key or brand_key in seen:
                continue
            seen.add(brand_key)
            if re.search(rf"\b{re.escape(brand_key)}\b", text):
                return brand.strip()
        return None

    def _extract_budget(
        self,
        question: str,
        *,
        filters: InventorySearchFilters,
    ) -> tuple[float | None, float | None]:
        budget_min = filters.min_price
        budget_max = filters.max_price

        range_match = self.RANGE_PATTERN.search(question)
        if range_match:
            first = float(range_match.group(1))
            second = float(range_match.group(2))
            budget_min = min(first, second) if budget_min is None else budget_min
            budget_max = max(first, second) if budget_max is None else budget_max

        max_match = self.MAX_PRICE_PATTERN.search(question)
        if max_match and budget_max is None:
            budget_max = float(max_match.group(1))

        min_match = self.MIN_PRICE_PATTERN.search(question)
        if min_match and budget_min is None:
            budget_min = float(min_match.group(1))

        return budget_min, budget_max

    def _extract_quality_level(self, text: str) -> str | None:
        if self._has_any(text, self.PREMIUM_HINTS):
            return "premium"
        if self._has_any(text, self.BUDGET_HINTS):
            return "budget"
        return None

    def _extract_keyword_matches(self, text: str, keyword_map: dict[str, tuple[str, ...]]) -> list[str]:
        matches: list[str] = []
        for label, phrases in keyword_map.items():
            if self._has_any(text, phrases):
                matches.append(label)
        return matches

    def _extract_avoid_product_types(self, text: str) -> list[str]:
        avoided: list[str] = []
        for product_type, synonyms in self.ontology.PRODUCT_SYNONYMS.items():
            for synonym in synonyms:
                normalized_synonym = normalize_inventory_text(synonym)
                if not normalized_synonym:
                    continue
                if (
                    f"not {normalized_synonym}" in text
                    or f"no {normalized_synonym}" in text
                    or f"avoid {normalized_synonym}" in text
                ):
                    avoided.append(product_type)
                    break
        return avoided

    @staticmethod
    def _estimate_confidence(
        *,
        product_type: str | None,
        category: str | None,
        brand: str | None,
        budget_min: float | None,
        budget_max: float | None,
        quality_level: str | None,
        feature_requirements: tuple[str, ...],
        use_cases: tuple[str, ...],
        selected_product_ids: tuple[str, ...],
    ) -> float:
        score = 0.0
        if product_type:
            score += 0.28
        if category:
            score += 0.14
        if brand:
            score += 0.12
        if budget_min is not None or budget_max is not None:
            score += 0.16
        if quality_level:
            score += 0.1
        if feature_requirements:
            score += min(0.12, 0.04 * len(feature_requirements))
        if use_cases:
            score += min(0.1, 0.05 * len(use_cases))
        if selected_product_ids:
            score += 0.22
        return round(min(1.0, score), 3)

    @staticmethod
    def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)
