from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


def normalize_inventory_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = re.sub(r"[^a-z0-9\s+-]", " ", text.casefold())
    return " ".join(normalized.split())


class ProductOntology:
    """Small deterministic ecommerce ontology used before ranking and generation."""

    PRODUCT_SYNONYMS: dict[str, tuple[str, ...]] = {
        "headphones": ("headphone", "headphones", "headset", "headsets", "over ear", "over-ear", "anc headphones"),
        "earbuds": ("earbud", "earbuds", "in ear", "in-ear", "true wireless"),
        "speaker": ("speaker", "speakers", "studio monitor", "monitor speaker", "monitor speakers"),
        "microphone": ("microphone", "microphones", "mic", "mics", "podcast mic", "usb mic"),
        "laptop": ("laptop", "laptops", "notebook", "notebooks", "ultrabook", "ultrabooks"),
        "keyboard": ("keyboard", "keyboards"),
        "mouse": ("mouse", "mice"),
        "watch": ("watch", "watches", "smart watch", "smartwatch", "smartwatches"),
        "chair": ("chair", "chairs"),
        "desk": ("desk", "desks", "standing desk", "desk converter"),
        "bag": ("bag", "bags", "backpack", "backpacks", "case", "cases"),
        "dock": ("dock", "docks", "docking station", "display station", "usb-c hub", "hub"),
        "printer": ("printer", "printers", "laser printer"),
        "webcam": ("webcam", "webcams", "camera", "cameras"),
        "monitor": ("monitor", "monitors", "display", "displays", "screen", "screens"),
        "bike": ("bike", "bikes", "bicycle", "bicycles", "cycle", "cycles"),
    }

    PRODUCT_FAMILIES: dict[str, str] = {
        "headphones": "audio_listening",
        "earbuds": "audio_listening",
        "speaker": "audio_speaker",
        "microphone": "audio_capture",
        "laptop": "computing_core",
        "keyboard": "computing_input",
        "mouse": "computing_input",
        "watch": "wearable",
        "chair": "furniture",
        "desk": "furniture",
        "bag": "carry_accessory",
        "dock": "computing_accessory",
        "printer": "office_equipment",
        "webcam": "video_capture",
        "monitor": "display",
        "bike": "transport",
    }

    DEFAULT_CATEGORY_BY_TYPE: dict[str, str] = {
        "headphones": "Audio",
        "earbuds": "Audio",
        "speaker": "Audio",
        "microphone": "Audio",
        "laptop": "Computing",
        "keyboard": "Computing",
        "mouse": "Computing",
        "dock": "Computing",
        "webcam": "Accessories",
        "monitor": "Computing",
        "watch": "Wearables",
        "chair": "Office",
        "desk": "Office",
        "bag": "Accessories",
        "printer": "Office",
        "bike": "Transport",
    }

    CROSS_SELL_COMPATIBILITY: dict[str, set[str]] = {
        "laptop": {"mouse", "keyboard", "dock", "bag", "monitor", "webcam", "headphones"},
        "headphones": {"microphone", "bag"},
        "earbuds": {"bag"},
        "microphone": {"headphones", "speaker"},
        "desk": {"chair", "monitor", "dock", "keyboard", "mouse"},
        "chair": {"desk"},
        "watch": {"earbuds", "headphones"},
        "printer": {"laptop"},
    }

    GENERIC_RELATION_TAGS = {
        "active",
        "available",
        "bluetooth",
        "budget",
        "customer",
        "office",
        "portable",
        "premium",
        "pro",
        "travel",
        "usb",
        "usb-c",
        "wireless",
    }

    def detect_product_type(self, text: str | None = None, product: object | None = None) -> str | None:
        searchable = self._searchable_product_text(text=text, product=product)
        if not searchable:
            return None

        name_text = self._product_signal_text(product, "name")
        category_text = self._product_signal_text(product, "category")
        brand_text = self._product_signal_text(product, "brand")
        tags = {
            normalize_inventory_text(tag)
            for tag in (getattr(product, "tags", None) or [])
            if isinstance(tag, str) and normalize_inventory_text(tag)
        }

        best_type: str | None = None
        best_score = 0
        for product_type, synonyms in self.PRODUCT_SYNONYMS.items():
            score = 0
            normalized_product_type = normalize_inventory_text(product_type)
            for synonym in synonyms:
                normalized_synonym = normalize_inventory_text(synonym)
                if not normalized_synonym:
                    continue
                if self._contains_phrase(searchable, normalized_synonym):
                    score = max(score, len(normalized_synonym.split()) * 2)
                    if name_text and self._contains_phrase(name_text, normalized_synonym):
                        score += 2
                    if category_text and self._contains_phrase(category_text, normalized_synonym):
                        score += 2
                    if brand_text and self._contains_phrase(brand_text, normalized_synonym):
                        score += 1
                    if any(self._contains_phrase(tag, normalized_synonym) for tag in tags):
                        score += 3
            if normalized_product_type in tags:
                score += 3
            default_category = normalize_inventory_text(self.category_for_product_type(product_type))
            if default_category and category_text == default_category:
                score += 2
            if score > best_score:
                best_type = product_type
                best_score = score
        return best_type

    def product_family(self, product_type: str | None) -> str | None:
        if product_type is None:
            return None
        return self.PRODUCT_FAMILIES.get(product_type)

    def category_for_product_type(self, product_type: str | None) -> str | None:
        if product_type is None:
            return None
        return self.DEFAULT_CATEGORY_BY_TYPE.get(product_type)

    def product_family_for_product(self, product: object) -> str | None:
        return self.product_family(self.detect_product_type(product=product))

    def same_product_family(self, a: object, b: object) -> bool:
        a_family = self.product_family_for_product(a)
        b_family = self.product_family_for_product(b)
        return bool(a_family and b_family and a_family == b_family)

    def valid_alternative(self, primary: object, candidate: object) -> bool:
        if self._product_id(primary) == self._product_id(candidate):
            return False

        primary_type = self.detect_product_type(product=primary)
        candidate_type = self.detect_product_type(product=candidate)
        if primary_type and candidate_type:
            if primary_type == candidate_type:
                return True
            return self.product_family(primary_type) == self.product_family(candidate_type) == "audio_listening"

        if self._same_category(primary, candidate):
            primary_tags = self.meaningful_tags(primary)
            candidate_tags = self.meaningful_tags(candidate)
            return bool(primary_tags.intersection(candidate_tags)) or not primary_tags or not candidate_tags
        return False

    def valid_cross_sell(self, primary: object, candidate: object, *, explicit_cross_sell: bool = False) -> bool:
        if not explicit_cross_sell or self._product_id(primary) == self._product_id(candidate):
            return False
        primary_type = self.detect_product_type(product=primary)
        candidate_type = self.detect_product_type(product=candidate)
        if not primary_type or not candidate_type or primary_type == candidate_type:
            return False
        if candidate_type in self.CROSS_SELL_COMPATIBILITY.get(primary_type, set()):
            return True
        if primary_type in self.CROSS_SELL_COMPATIBILITY.get(candidate_type, set()):
            return True
        return False

    def explain_relationship(self, primary: object, candidate: object) -> str:
        primary_type = self.detect_product_type(product=primary)
        candidate_type = self.detect_product_type(product=candidate)
        if primary_type and candidate_type and primary_type == candidate_type:
            return f"Both products are {primary_type}."
        if primary_type and candidate_type:
            primary_family = self.product_family(primary_type)
            candidate_family = self.product_family(candidate_type)
            if primary_family and primary_family == candidate_family:
                return f"{candidate_type} is in the same {primary_family.replace('_', ' ')} family as {primary_type}."
            if candidate_type in self.CROSS_SELL_COMPATIBILITY.get(primary_type, set()):
                return f"{candidate_type} is a complementary add-on for {primary_type}."
        if self._same_category(primary, candidate):
            category = self._text_attr(primary, "category")
            return f"Both products are in the {category} category."
        return "The products are not close substitutes."

    def relation_score(self, requested_product_type: str | None, product: object) -> int:
        if not requested_product_type:
            return 0
        product_type = self.detect_product_type(product=product)
        if product_type == requested_product_type:
            return 3
        requested_family = self.product_family(requested_product_type)
        product_family = self.product_family(product_type)
        if requested_family and requested_family == product_family:
            return 2
        requested_category = self.category_for_product_type(requested_product_type)
        if requested_category and self._text_attr(product, "category").casefold() == requested_category.casefold():
            return 1
        return 0

    def meaningful_tags(self, product: object) -> set[str]:
        tags = getattr(product, "tags", None) or []
        return {
            normalize_inventory_text(tag)
            for tag in tags
            if normalize_inventory_text(tag) and normalize_inventory_text(tag) not in self.GENERIC_RELATION_TAGS
        }

    def _searchable_product_text(self, *, text: str | None, product: object | None) -> str:
        parts: list[str] = []
        if text:
            parts.append(text)
        if product is not None:
            for attr in (
                "name",
                "sku",
                "category",
                "brand",
                "short_description",
                "full_description",
                "snippet",
                "status",
            ):
                value = getattr(product, attr, None)
                if isinstance(value, str):
                    parts.append(value)
            tags = getattr(product, "tags", None) or []
            parts.extend(str(tag) for tag in tags)
            attributes = getattr(product, "attributes", None) or {}
            metadata = getattr(product, "metadata", None) or {}
            parts.extend(self._flatten_mapping_text(attributes))
            parts.extend(self._flatten_mapping_text(metadata))
        return normalize_inventory_text(" ".join(parts))

    def _flatten_mapping_text(self, mapping: dict[str, Any]) -> Iterable[str]:
        for key, value in mapping.items():
            if isinstance(value, dict):
                yield from self._flatten_mapping_text(value)
            else:
                yield f"{key} {value}"

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        if " " in phrase:
            return phrase in text
        return bool(re.search(rf"\b{re.escape(phrase)}\b", text))

    @staticmethod
    def _product_id(product: object) -> str | None:
        value = getattr(product, "product_id", None)
        return value if isinstance(value, str) else None

    @staticmethod
    def _text_attr(product: object, attr: str) -> str:
        value = getattr(product, attr, None)
        return value if isinstance(value, str) else ""

    def _product_signal_text(self, product: object | None, attr: str) -> str:
        if product is None:
            return ""
        return normalize_inventory_text(self._text_attr(product, attr))

    def _same_category(self, primary: object, candidate: object) -> bool:
        primary_category = self._text_attr(primary, "category")
        candidate_category = self._text_attr(candidate, "category")
        return bool(primary_category and candidate_category and primary_category.casefold() == candidate_category.casefold())
