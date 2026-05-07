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
        "speakerphone": ("speakerphone", "speaker phone", "conference speakerphone", "meeting room speaker"),
        "headset": ("headset", "headsets", "office headset", "call headset", "support headset", "boom mic"),
        "headphones": ("headphone", "headphones", "over ear", "over-ear", "anc headphones", "monitor headphones"),
        "earbuds": ("earbud", "earbuds", "in ear", "in-ear", "true wireless"),
        "portable_speaker": ("portable speaker", "bluetooth speaker", "outdoor speaker"),
        "speaker": ("speaker", "speakers", "studio monitor", "monitor speaker", "monitor speakers"),
        "microphone": ("microphone", "microphones", "mic", "mics", "podcast mic", "usb mic", "xlr mic"),
        "laptop_sleeve": ("laptop sleeve", "notebook sleeve", "computer sleeve"),
        "laptop_stand": ("laptop stand", "notebook stand", "foldable stand", "viewstand"),
        "laptop": ("laptop", "laptops", "notebook", "notebooks", "ultrabook", "ultrabooks"),
        "desktop": ("desktop", "mini desktop", "desktop computer", "pc"),
        "tablet": ("tablet", "tablets"),
        "phone_case": ("phone case", "smartphone case", "mobile case", "protective case"),
        "phone": ("phone", "phones", "smartphone", "smartphones", "mobile phone"),
        "charger": ("charger", "chargers", "gan charger", "power adapter", "usb-c charger"),
        "power_bank": ("power bank", "powerbank", "battery bank", "portable battery"),
        "cable_pack": ("cable pack", "cable kit", "cables", "cablecraft"),
        "tech_pouch": ("tech pouch", "organizer pouch", "electronics pouch"),
        "cleaning_kit": ("cleaning kit", "screen cleaner", "clean kit"),
        "keyboard": ("keyboard", "keyboards"),
        "mouse": ("mouse", "mice"),
        "fitness_band": ("fitness band", "tracker", "fitness tracker", "activity band"),
        "watch": ("watch", "watches", "smart watch", "smartwatch", "smartwatches"),
        "lamp": ("lamp", "task lamp", "desk lamp", "lighting"),
        "whiteboard": ("whiteboard", "white board"),
        "organizer": ("organizer", "desk tray", "paper tray"),
        "filing_cabinet": ("filing cabinet", "file cabinet", "file storage", "secure file storage", "cabinet"),
        "chair": ("chair", "chairs"),
        "desk": ("desk", "desks", "standing desk", "desk converter"),
        "bag": ("bag", "bags", "backpack", "backpacks"),
        "dock": ("dock", "docks", "docking station", "display station", "usb-c hub", "hub"),
        "printer": ("printer", "printers", "laser printer"),
        "webcam": ("webcam", "webcams", "meeting camera"),
        "security_camera": ("security camera", "indoor cam", "indoor camera", "smart camera"),
        "monitor": ("monitor", "monitors", "external display", "gaming monitor", "qhd monitor", "ultrawide monitor"),
        "router": ("router", "routers", "wi-fi router", "wifi router"),
        "mesh_wifi": ("mesh", "mesh wifi", "mesh wi-fi", "mesh router"),
        "wifi_extender": ("wi-fi extender", "wifi extender", "range extender", "coverage extender"),
        "hotspot": ("hotspot", "5g hotspot", "mobile hotspot"),
        "network_switch": ("network switch", "gigabit switch", "ethernet switch"),
        "poe_injector": ("poe injector", "poe"),
        "portable_ssd": ("portable ssd", "ssd", "solid state drive"),
        "hard_drive": ("hard drive", "hdd", "desktop drive", "backup drive"),
        "microsd": ("microsd", "micro sd", "micro-sd", "memory card", "sd card"),
        "smart_lock": ("smart lock", "keyless lock", "door lock"),
        "smart_bulb": ("smart bulb", "bulb"),
        "light_strip": ("light strip", "strip light"),
        "room_sensor": ("room sensor", "climate sensor", "sensor"),
        "robot_vacuum": ("robot vacuum", "vacuum", "slimvac"),
        "bike": ("bike", "bikes", "bicycle", "bicycles", "cycle", "cycles"),
    }

    PRODUCT_FAMILIES: dict[str, str] = {
        "speakerphone": "audio_conference",
        "headset": "audio_listening",
        "headphones": "audio_listening",
        "earbuds": "audio_listening",
        "portable_speaker": "audio_speaker",
        "speaker": "audio_speaker",
        "microphone": "audio_capture",
        "laptop_sleeve": "computing_accessory",
        "laptop_stand": "computing_accessory",
        "laptop": "computing_core",
        "desktop": "computing_core",
        "tablet": "computing_core",
        "phone_case": "mobile_accessory",
        "phone": "mobile_core",
        "charger": "power_accessory",
        "power_bank": "power_accessory",
        "cable_pack": "accessory",
        "tech_pouch": "carry_accessory",
        "cleaning_kit": "accessory",
        "keyboard": "computing_input",
        "mouse": "computing_input",
        "fitness_band": "wearable",
        "watch": "wearable",
        "filing_cabinet": "furniture_storage",
        "chair": "furniture",
        "desk": "furniture",
        "lamp": "office_accessory",
        "whiteboard": "office_equipment",
        "organizer": "office_accessory",
        "bag": "carry_accessory",
        "dock": "computing_accessory",
        "printer": "office_equipment",
        "webcam": "video_capture",
        "security_camera": "security_device",
        "monitor": "display",
        "router": "networking",
        "mesh_wifi": "networking",
        "wifi_extender": "networking",
        "hotspot": "networking",
        "network_switch": "networking",
        "poe_injector": "networking",
        "portable_ssd": "storage",
        "hard_drive": "storage",
        "microsd": "storage",
        "smart_lock": "smart_home",
        "smart_bulb": "smart_home",
        "light_strip": "smart_home",
        "room_sensor": "smart_home",
        "robot_vacuum": "home_appliance",
        "bike": "transport",
    }

    DEFAULT_CATEGORY_BY_TYPE: dict[str, str] = {
        "speakerphone": "Audio",
        "headset": "Audio",
        "headphones": "Audio",
        "earbuds": "Audio",
        "portable_speaker": "Audio",
        "speaker": "Audio",
        "microphone": "Audio",
        "laptop_sleeve": "Accessories",
        "laptop_stand": "Accessories",
        "laptop": "Computing",
        "desktop": "Computing",
        "tablet": "Computing",
        "phone_case": "Mobile",
        "phone": "Mobile",
        "charger": "Mobile",
        "power_bank": "Mobile",
        "cable_pack": "Accessories",
        "tech_pouch": "Accessories",
        "cleaning_kit": "Accessories",
        "keyboard": "Computing",
        "mouse": "Computing",
        "dock": "Computing",
        "webcam": "Computing",
        "monitor": "Computing",
        "watch": "Wearables",
        "fitness_band": "Wearables",
        "filing_cabinet": "Office",
        "chair": "Office",
        "desk": "Office",
        "lamp": "Office",
        "whiteboard": "Office",
        "organizer": "Office",
        "bag": "Accessories",
        "printer": "Office",
        "security_camera": "Smart Home",
        "router": "Networking",
        "mesh_wifi": "Networking",
        "wifi_extender": "Networking",
        "hotspot": "Networking",
        "network_switch": "Networking",
        "poe_injector": "Networking",
        "portable_ssd": "Storage",
        "hard_drive": "Storage",
        "microsd": "Storage",
        "smart_lock": "Smart Home",
        "smart_bulb": "Smart Home",
        "light_strip": "Smart Home",
        "room_sensor": "Smart Home",
        "robot_vacuum": "Smart Home",
        "bike": "Transport",
    }

    CROSS_SELL_COMPATIBILITY: dict[str, set[str]] = {
        "laptop": {
            "charger",
            "cleaning_kit",
            "dock",
            "bag",
            "headphones",
            "headset",
            "keyboard",
            "laptop_sleeve",
            "laptop_stand",
            "monitor",
            "mouse",
            "webcam",
        },
        "phone": {"charger", "cleaning_kit", "earbuds", "phone_case", "power_bank", "tech_pouch"},
        "tablet": {"charger", "cleaning_kit", "keyboard", "microsd", "power_bank", "tech_pouch"},
        "headphones": {"bag", "microphone", "tech_pouch"},
        "headset": {"webcam", "speakerphone"},
        "earbuds": {"bag", "phone_case", "power_bank", "tech_pouch"},
        "microphone": {"headphones", "headset", "lamp", "webcam"},
        "desk": {"chair", "dock", "keyboard", "lamp", "laptop_stand", "monitor", "mouse", "organizer"},
        "chair": {"desk", "lamp"},
        "watch": {"earbuds", "headphones"},
        "printer": {"laptop", "network_switch"},
        "router": {"mesh_wifi", "network_switch", "wifi_extender"},
        "security_camera": {"microsd", "poe_injector", "router"},
    }

    GENERIC_RELATION_TAGS = {
        "active",
        "available",
        "bluetooth",
        "budget",
        "customer",
        "desktop",
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
                    score = max(score, len(normalized_synonym.split()) * 3)
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
            if (
                product_type == "portable_speaker"
                and "speaker" in tags
                and tags.intersection({"bluetooth", "outdoor", "portable"})
            ):
                score += 4
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
