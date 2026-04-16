from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.inventory.ontology import ProductOntology, normalize_inventory_text
from app.inventory.preferences import InventoryPreferenceProfile


@dataclass(frozen=True)
class ProductEvidenceScore:
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    category_match: float = 0.0
    brand_match: float = 0.0
    product_type_match: float = 0.0
    family_match: float = 0.0
    price_fit: float = 0.0
    stock_fit: float = 0.0
    metadata_match: float = 0.0
    premium_fit: float = 0.0
    budget_fit: float = 0.0
    unrelated_category_penalty: float = 0.0
    out_of_stock_penalty: float = 0.0
    final_score: float = 0.0
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "semantic_score": self.semantic_score,
            "lexical_score": self.lexical_score,
            "category_match": self.category_match,
            "brand_match": self.brand_match,
            "product_type_match": self.product_type_match,
            "family_match": self.family_match,
            "price_fit": self.price_fit,
            "stock_fit": self.stock_fit,
            "metadata_match": self.metadata_match,
            "premium_fit": self.premium_fit,
            "budget_fit": self.budget_fit,
            "unrelated_category_penalty": self.unrelated_category_penalty,
            "out_of_stock_penalty": self.out_of_stock_penalty,
            "final_score": self.final_score,
            "reasons": list(self.reasons),
        }


class EcommerceReranker:
    FEATURE_TERMS: dict[str, tuple[str, ...]] = {
        "wireless": ("wireless", "bluetooth"),
        "noise_cancellation": ("noise cancellation", "noise cancelling", "anc"),
        "usb_c": ("usb c", "usb-c", "type c"),
        "battery_life": ("battery", "battery life", "hours"),
        "ergonomic": ("ergonomic", "lumbar"),
        "gps": ("gps",),
        "heart_rate": ("heart rate", "heart-rate"),
        "portable": ("portable", "travel", "commute"),
        "premium": ("premium", "flagship", "pro", "elite", "ultra"),
    }
    USE_CASE_TERMS: dict[str, tuple[str, ...]] = {
        "office_calls": ("office call", "office calls", "meeting", "meetings", "calls", "webinar"),
        "gaming": ("gaming", "game"),
        "travel": ("travel", "commute", "commuter"),
        "fitness": ("fitness", "workout", "running", "health"),
        "podcasting": ("podcast", "podcasting", "recording", "webinar"),
        "business": ("business", "manager", "analyst", "client"),
        "editing": ("editing", "studio", "content"),
    }
    PREMIUM_TERMS = ("premium", "flagship", "pro", "elite", "ultra", "high end", "high-end", "luxury")

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()

    def score_product(
        self,
        product: object,
        *,
        preferences: InventoryPreferenceProfile,
        semantic_score: float,
        lexical_score: float,
        assistant_mode: str = "support",
    ) -> ProductEvidenceScore:
        normalized_semantic = self._clamp(semantic_score)
        normalized_lexical = self._clamp(lexical_score)
        product_type = self.ontology.detect_product_type(product=product)
        product_family = self.ontology.product_family(product_type)
        searchable_text = self._product_text(product)

        category_match = self._category_match(product, preferences)
        brand_match = self._brand_match(product, preferences)
        product_type_match = 1.0 if preferences.product_type and product_type == preferences.product_type else 0.0
        family_match = (
            1.0
            if preferences.product_family and product_family and preferences.product_family == product_family
            else 0.0
        )
        price_fit = self._price_fit(product, preferences)
        stock_fit = self._stock_fit(product)
        metadata_match = self._metadata_match(searchable_text, preferences)
        premium_fit = self._premium_fit(searchable_text, preferences)
        budget_fit = self._budget_fit(product, preferences)
        unrelated_category_penalty = self._unrelated_category_penalty(
            product=product,
            product_type=product_type,
            product_family=product_family,
            preferences=preferences,
        )
        out_of_stock_penalty = self._out_of_stock_penalty(
            product=product,
            preferences=preferences,
            assistant_mode=assistant_mode,
        )

        raw_score = (
            (normalized_semantic * 0.18)
            + (normalized_lexical * 0.2)
            + (product_type_match * 0.2)
            + (family_match * 0.1)
            + (category_match * 0.08)
            + (brand_match * 0.05)
            + (price_fit * 0.08)
            + (stock_fit * 0.04)
            + (metadata_match * 0.04)
            + (premium_fit * 0.03)
            + (budget_fit * 0.03)
            - unrelated_category_penalty
            - out_of_stock_penalty
        )
        final_score = round(self._clamp(raw_score), 4)

        return ProductEvidenceScore(
            semantic_score=round(normalized_semantic, 4),
            lexical_score=round(normalized_lexical, 4),
            category_match=round(category_match, 4),
            brand_match=round(brand_match, 4),
            product_type_match=round(product_type_match, 4),
            family_match=round(family_match, 4),
            price_fit=round(price_fit, 4),
            stock_fit=round(stock_fit, 4),
            metadata_match=round(metadata_match, 4),
            premium_fit=round(premium_fit, 4),
            budget_fit=round(budget_fit, 4),
            unrelated_category_penalty=round(unrelated_category_penalty, 4),
            out_of_stock_penalty=round(out_of_stock_penalty, 4),
            final_score=final_score,
            reasons=self._build_reasons(
                preferences=preferences,
                product_type=product_type,
                product_family=product_family,
                category_match=category_match,
                brand_match=brand_match,
                price_fit=price_fit,
                stock_fit=stock_fit,
                metadata_match=metadata_match,
                unrelated_category_penalty=unrelated_category_penalty,
            ),
        )

    def _build_reasons(
        self,
        *,
        preferences: InventoryPreferenceProfile,
        product_type: str | None,
        product_family: str | None,
        category_match: float,
        brand_match: float,
        price_fit: float,
        stock_fit: float,
        metadata_match: float,
        unrelated_category_penalty: float,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if preferences.product_type and product_type == preferences.product_type:
            reasons.append(f"exact product type match: {product_type}")
        elif preferences.product_family and product_family == preferences.product_family:
            reasons.append(f"same product family: {product_family}")
        if category_match >= 1.0:
            reasons.append("category matches request")
        if brand_match >= 1.0:
            reasons.append("brand matches request")
        if price_fit >= 1.0 and (preferences.budget_min is not None or preferences.budget_max is not None):
            reasons.append("price is inside requested budget")
        if stock_fit >= 1.0:
            reasons.append("in stock")
        if metadata_match > 0:
            reasons.append("metadata/features match requested need")
        if unrelated_category_penalty > 0:
            reasons.append("penalized as unrelated or weakly related")
        return tuple(reasons[:8])

    def _category_match(self, product: object, preferences: InventoryPreferenceProfile) -> float:
        if not preferences.category:
            return 0.0
        product_category = self._text_attr(product, "category")
        if product_category.casefold() == preferences.category.casefold():
            return 1.0
        return 0.0

    def _brand_match(self, product: object, preferences: InventoryPreferenceProfile) -> float:
        if not preferences.brand:
            return 0.0
        brand = self._text_attr(product, "brand")
        return 1.0 if brand.casefold() == preferences.brand.casefold() else 0.0

    def _price_fit(self, product: object, preferences: InventoryPreferenceProfile) -> float:
        price = self._number_attr(product, "price")
        if preferences.budget_min is None and preferences.budget_max is None:
            return 0.0
        if price is None:
            return 0.15
        if preferences.budget_min is not None and price < preferences.budget_min:
            gap = preferences.budget_min - price
            return self._clamp(1.0 - gap / max(preferences.budget_min, 1.0))
        if preferences.budget_max is not None and price > preferences.budget_max:
            gap = price - preferences.budget_max
            return self._clamp(1.0 - gap / max(preferences.budget_max, 1.0))
        return 1.0

    def _stock_fit(self, product: object) -> float:
        stock = self._number_attr(product, "stock")
        if stock is None:
            return 0.2
        if stock <= 0:
            return 0.0
        return 1.0

    def _metadata_match(self, searchable_text: str, preferences: InventoryPreferenceProfile) -> float:
        requirements = list(preferences.feature_requirements) + list(preferences.use_cases)
        if not requirements:
            return 0.0
        matched = 0
        for requirement in requirements:
            terms = self.FEATURE_TERMS.get(requirement) or self.USE_CASE_TERMS.get(requirement) or (
                requirement.replace("_", " "),
            )
            if any(term in searchable_text for term in terms):
                matched += 1
        return matched / len(requirements)

    def _premium_fit(self, searchable_text: str, preferences: InventoryPreferenceProfile) -> float:
        if preferences.quality_level != "premium":
            return 0.0
        return 1.0 if any(term in searchable_text for term in self.PREMIUM_TERMS) else 0.0

    def _budget_fit(self, product: object, preferences: InventoryPreferenceProfile) -> float:
        if preferences.quality_level != "budget" and preferences.budget_max is None:
            return 0.0
        price = self._number_attr(product, "price")
        if price is None:
            return 0.1
        if preferences.budget_max is not None and preferences.budget_max > 0:
            return self._clamp(1.0 - (price / preferences.budget_max) * 0.35)
        return 1.0 / (1.0 + max(price, 0.0) / 1000.0)

    def _unrelated_category_penalty(
        self,
        *,
        product: object,
        product_type: str | None,
        product_family: str | None,
        preferences: InventoryPreferenceProfile,
    ) -> float:
        if not preferences.product_type and not preferences.category:
            return 0.0
        if preferences.product_type:
            if product_type == preferences.product_type:
                return 0.0
            if preferences.product_family and product_family == preferences.product_family:
                return 0.04
            return 0.35
        if preferences.category and self._text_attr(product, "category").casefold() != preferences.category.casefold():
            return 0.2
        return 0.0

    def _out_of_stock_penalty(
        self,
        *,
        product: object,
        preferences: InventoryPreferenceProfile,
        assistant_mode: str,
    ) -> float:
        stock = self._number_attr(product, "stock")
        if stock is None or stock > 0:
            return 0.0
        if preferences.needs_in_stock or assistant_mode == "sales":
            return 0.25
        return 0.06

    def _product_text(self, product: object) -> str:
        parts: list[str] = []
        for attr in ("name", "sku", "category", "brand", "short_description", "full_description", "snippet", "status"):
            value = getattr(product, attr, None)
            if isinstance(value, str):
                parts.append(value)
        tags = getattr(product, "tags", None) or []
        parts.extend(str(tag) for tag in tags)
        for mapping_attr in ("attributes", "metadata"):
            mapping = getattr(product, mapping_attr, None) or {}
            parts.extend(self._flatten_mapping_text(mapping))
        return normalize_inventory_text(" ".join(parts))

    def _flatten_mapping_text(self, mapping: dict[str, Any]) -> list[str]:
        parts: list[str] = []
        for key, value in mapping.items():
            if isinstance(value, dict):
                parts.extend(self._flatten_mapping_text(value))
            else:
                parts.append(f"{key} {value}")
        return parts

    @staticmethod
    def _text_attr(product: object, attr: str) -> str:
        value = getattr(product, attr, None)
        return value if isinstance(value, str) else ""

    @staticmethod
    def _number_attr(product: object, attr: str) -> float | None:
        value = getattr(product, attr, None)
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float):
            return float(value)
        return None

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
