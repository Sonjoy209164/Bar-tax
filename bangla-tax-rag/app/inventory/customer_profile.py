from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.inventory.identity_store import IdentityStore

_PROFILES_PATH = Path("data/customer_profiles/profiles_store.jsonl")
_identity_store = IdentityStore()
logger = logging.getLogger(__name__)

FORGET_PHRASES = (
    "amar preference delete",
    "preference delete kore dao",
    "preference reset",
    "preference ভুলে যাও",
    "সব preference মুছে দাও",
    "forget my preferences",
    "delete my preferences",
    "reset my preferences",
    "clear my memory",
    "memory delete kore dao",
    "memory mochhe dao",
    "amar memory delete",
)

SHOW_PROFILE_PHRASES = (
    "amar saved preference ki",
    "amar preference ki",
    "amar profile",
    "what are my preferences",
    "show my preferences",
    "saved preference dekhao",
    "আমার preference কী",
    "আমার প্রোফাইল",
)


@dataclass
class CustomerProfile:
    session_id: str
    preferred_language: str | None = None
    sizes: dict[str, str] = field(default_factory=dict)
    favorite_colors: list[str] = field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    preferred_categories: list[str] = field(default_factory=list)
    skin_type: str | None = None
    delivery_area: str | None = None
    fragrance_family: str | None = None
    notes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            not self.preferred_language
            and not self.sizes
            and not self.favorite_colors
            and self.budget_min is None
            and self.budget_max is None
            and not self.preferred_categories
            and not self.skin_type
            and not self.delivery_area
            and not self.fragrance_family
        )

    def summary_text(self) -> str:
        if self.is_empty():
            return "No saved preferences for this session."
        lines: list[str] = ["Saved Preferences:"]
        if self.preferred_language:
            lines.append(f"  Language: {self.preferred_language}")
        if self.sizes:
            size_str = ", ".join(f"{k}: {v}" for k, v in self.sizes.items())
            lines.append(f"  Sizes: {size_str}")
        if self.favorite_colors:
            lines.append(f"  Favorite Colors: {', '.join(self.favorite_colors)}")
        if self.budget_min is not None or self.budget_max is not None:
            if self.budget_max:
                lines.append(f"  Budget: up to BDT {self.budget_max:,.0f}")
            else:
                lines.append(f"  Budget: from BDT {self.budget_min:,.0f}")
        if self.preferred_categories:
            lines.append(f"  Categories: {', '.join(self.preferred_categories)}")
        if self.skin_type:
            lines.append(f"  Skin Type: {self.skin_type}")
        if self.delivery_area:
            lines.append(f"  Delivery Area: {self.delivery_area}")
        if self.fragrance_family:
            lines.append(f"  Fragrance Family: {self.fragrance_family}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "preferred_language": self.preferred_language,
            "sizes": self.sizes,
            "favorite_colors": self.favorite_colors,
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "preferred_categories": self.preferred_categories,
            "skin_type": self.skin_type,
            "delivery_area": self.delivery_area,
            "fragrance_family": self.fragrance_family,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CustomerProfile:
        profile = cls(session_id=data.get("session_id", "unknown"))
        profile.preferred_language = data.get("preferred_language")
        profile.sizes = data.get("sizes") or {}
        profile.favorite_colors = data.get("favorite_colors") or []
        profile.budget_min = data.get("budget_min")
        profile.budget_max = data.get("budget_max")
        profile.preferred_categories = data.get("preferred_categories") or []
        profile.skin_type = data.get("skin_type")
        profile.delivery_area = data.get("delivery_area")
        profile.fragrance_family = data.get("fragrance_family")
        return profile


_SIZE_PATTERN = re.compile(
    r"\b(?:size|saiz|সাইজ)\s*[:-]?\s*(XS|S|M|L|XL|XXL|XXXL|\d{2})\b",
    re.IGNORECASE,
)
_SHOE_SIZE_PATTERN = re.compile(r"\b(?:shoe|boot|loafer|জুতা)?\s*size\s*[:-]?\s*(\d{2})\b", re.IGNORECASE)
_BUDGET_PATTERN = re.compile(
    r"\b(?:budget|বাজেট)\s*[:-]?\s*(?:normally|usually|সাধারণত)?\s*(?:BDT|৳|tk)?\s*(\d+(?:,\d+)?)\s*(?:er moddhe|এর মধ্যে|এর মধ্যে|বা কম)?",
    re.IGNORECASE,
)
_COLOR_PATTERN = re.compile(
    r"\b(?:color|colour|রং|রঙ)\s*[:-]?\s*(?:usually|সাধারণত|পছন্দ)?\s*([a-zঀ-৿]+(?:\s+[a-zঀ-৿]+)?)",
    re.IGNORECASE,
)
_SKIN_PATTERN = re.compile(r"\b(oily|dry|combination|sensitive|normal)\s*skin\b", re.IGNORECASE)
_SKIN_BANGLA = re.compile(r"(তৈলাক্ত|শুষ্ক|সংমিশ্রণ|সংবেদনশীল)\s*ত্বক")


KNOWN_COLORS = {
    "red", "blue", "green", "black", "white", "gold", "silver", "maroon",
    "navy", "pink", "purple", "orange", "yellow", "brown", "grey", "gray",
    "লাল", "নীল", "সবুজ", "কালো", "সাদা", "সোনালি", "গোল্ড",
}

KNOWN_CATEGORIES = {
    "saree", "bag", "shoes", "jewelry", "panjabi", "shirt", "cosmetics",
    "beauty", "perfume", "watch", "kurti", "salwar_kameez",
}


class CustomerProfileManager:
    """Manages customer profile memory within a session, with optional file persistence."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._profile: CustomerProfile = self._load_or_create()

    @property
    def profile(self) -> CustomerProfile:
        return self._profile

    def _load_or_create(self) -> CustomerProfile:
        # Check identity store first (cross-session, phone-linked)
        try:
            identity_data = _identity_store.get_or_create_profile(self._session_id)
            if identity_data and identity_data.get("phone"):
                return CustomerProfile.from_dict({**identity_data, "session_id": self._session_id})
        except Exception as exc:
            logger.debug("Identity store lookup failed: %s", exc)

        if _PROFILES_PATH.exists():
            with _PROFILES_PATH.open("r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        if data.get("session_id") == self._session_id:
                            return CustomerProfile.from_dict(data)
                    except (json.JSONDecodeError, KeyError):
                        continue
        return CustomerProfile(session_id=self._session_id)

    def link_phone(self, phone: str) -> None:
        """Link this session to a phone number for cross-session persistence."""
        try:
            self._profile.phone = phone  # type: ignore[attr-defined]
        except AttributeError:
            pass
        try:
            _identity_store.link_session(self._session_id, phone)
            _identity_store.save_session_profile(self._session_id, {**self._profile.to_dict(), "phone": phone})
        except Exception as exc:
            logger.debug("Identity store link_phone failed: %s", exc)

    def extract_and_update(self, text: str) -> list[str]:
        """Extract preferences from customer message, update profile, return confirmation lines."""
        updates: list[str] = []
        normalized = text.casefold()

        size_match = _SIZE_PATTERN.search(text)
        if size_match:
            size_val = size_match.group(1).upper()
            category_for_size = _infer_size_category(normalized)
            self._profile.sizes[category_for_size] = size_val
            updates.append(f"{category_for_size} size: {size_val}")

        shoe_size_match = _SHOE_SIZE_PATTERN.search(text)
        if shoe_size_match and "shoe" not in self._profile.sizes:
            self._profile.sizes["shoe"] = shoe_size_match.group(1)
            updates.append(f"shoe size: {shoe_size_match.group(1)}")

        budget_match = _BUDGET_PATTERN.search(text)
        if budget_match:
            budget_val = float(budget_match.group(1).replace(",", ""))
            self._profile.budget_max = budget_val
            updates.append(f"budget: up to BDT {budget_val:,.0f}")

        color_match = _COLOR_PATTERN.search(text)
        if color_match:
            color_val = color_match.group(1).strip().casefold()
            if color_val in KNOWN_COLORS and color_val not in self._profile.favorite_colors:
                self._profile.favorite_colors.append(color_val)
                updates.append(f"favorite color: {color_val}")

        skin_match = _SKIN_PATTERN.search(text)
        if skin_match:
            self._profile.skin_type = skin_match.group(1).lower()
            updates.append(f"skin type: {self._profile.skin_type}")

        skin_bangla_match = _SKIN_BANGLA.search(text)
        if skin_bangla_match and not self._profile.skin_type:
            bangla_to_eng = {"তৈলাক্ত": "oily", "শুষ্ক": "dry", "সংমিশ্রণ": "combination", "সংবেদনশীল": "sensitive"}
            self._profile.skin_type = bangla_to_eng.get(skin_bangla_match.group(1), "unknown")
            updates.append(f"skin type: {self._profile.skin_type}")

        if updates:
            self._persist()
        return updates

    def reset(self) -> str:
        self._profile = CustomerProfile(session_id=self._session_id)
        self._remove_from_store()
        return "Done. I cleared all saved preferences for this session."

    def is_forget_request(self, text: str) -> bool:
        normalized = text.casefold()
        return any(phrase in normalized for phrase in FORGET_PHRASES)

    def is_show_request(self, text: str) -> bool:
        normalized = text.casefold()
        return any(phrase in normalized for phrase in SHOW_PROFILE_PHRASES)

    def _persist(self) -> None:
        _PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict[str, Any]] = []
        if _PROFILES_PATH.exists():
            with _PROFILES_PATH.open("r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        if data.get("session_id") != self._session_id:
                            existing.append(data)
                    except json.JSONDecodeError:
                        continue
        existing.append(self._profile.to_dict())
        with _PROFILES_PATH.open("w", encoding="utf-8") as handle:
            for entry in existing:
                handle.write(json.dumps(entry, ensure_ascii=False))
                handle.write("\n")
        # Mirror into identity store when phone is available
        try:
            _identity_store.save_session_profile(self._session_id, self._profile.to_dict())
        except Exception as exc:
            logger.debug("Identity store persist failed: %s", exc)

    def _remove_from_store(self) -> None:
        if not _PROFILES_PATH.exists():
            return
        remaining: list[dict[str, Any]] = []
        with _PROFILES_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    if data.get("session_id") != self._session_id:
                        remaining.append(data)
                except json.JSONDecodeError:
                    continue
        with _PROFILES_PATH.open("w", encoding="utf-8") as handle:
            for entry in remaining:
                handle.write(json.dumps(entry, ensure_ascii=False))
                handle.write("\n")


def _infer_size_category(normalized_text: str) -> str:
    if any(w in normalized_text for w in ("shoe", "boot", "loafer", "sneaker", "জুতা", "জুতো")):
        return "shoe"
    if any(w in normalized_text for w in ("blouse", "ব্লাউজ")):
        return "blouse"
    if any(w in normalized_text for w in ("panjabi", "punjabi", "shirt", "শার্ট", "পাঞ্জাবি")):
        return "top"
    if any(w in normalized_text for w in ("pant", "trouser", "প্যান্ট")):
        return "bottom"
    return "general"
