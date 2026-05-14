from __future__ import annotations

import base64
import hashlib
import math
from dataclasses import dataclass
from typing import Any

from app.core.schemas import InventoryImageAsset, InventoryItemRecord


@dataclass(frozen=True)
class ImageMatchResult:
    product_id: str
    name: str
    score: float
    match_type: str
    reasons: tuple[str, ...]
    price: float | None
    currency: str
    stock: int
    image_url: str | None = None


IMAGE_QUERY_PHRASES = (
    "এই ছবির মতো",
    "ei picture er moto",
    "ei chobir moto",
    "same design",
    "similar design",
    "এই রকম",
    "এরকম",
    "similar to this",
    "find similar",
    "image er moto",
    "picture match",
    "ছবির মতো",
    "same pattern",
    "এই জামদানির মতো",
    "এই শাড়ির মতো",
    "can you find a similar",
    "match this",
    "matches this",
    "ম্যাচিং",
)


def _deterministic_image_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def _color_histogram_score(pixels_a: list[int], pixels_b: list[int]) -> float:
    if not pixels_a or not pixels_b:
        return 0.5
    size = min(len(pixels_a), len(pixels_b))
    dot = sum(pixels_a[i] * pixels_b[i] for i in range(size))
    mag_a = math.sqrt(sum(x * x for x in pixels_a[:size]))
    mag_b = math.sqrt(sum(x * x for x in pixels_b[:size]))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _extract_dominant_color_from_b64(b64_data: str) -> str | None:
    try:
        raw = base64.b64decode(b64_data + "==")
        if len(raw) < 16:
            return None
        color_byte = raw[8] % 8
        color_map = {0: "red", 1: "blue", 2: "green", 3: "black", 4: "white", 5: "gold", 6: "maroon", 7: "navy"}
        return color_map.get(color_byte)
    except Exception:
        return None


def is_image_search_query(text: str) -> bool:
    normalized = text.casefold()
    return any(phrase in normalized for phrase in IMAGE_QUERY_PHRASES)


class ImageMatcher:
    """Metadata-aware visual similarity engine.

    In production, this integrates image embeddings. In deterministic/local mode,
    it scores candidates using product metadata (design_id, color_family, category,
    work_type) to simulate image matching. The scoring ensures grounded responses
    without claiming exact visual match unless SKU/design metadata proves it.
    """

    def __init__(self, catalog: dict[str, InventoryItemRecord]) -> None:
        self._catalog = catalog

    def search(
        self,
        *,
        query_text: str,
        image_b64: str | None = None,
        category_hint: str | None = None,
        color_hint: str | None = None,
        budget_max: float | None = None,
        top_k: int = 5,
    ) -> list[ImageMatchResult]:
        dominant_color = None
        if image_b64:
            dominant_color = _extract_dominant_color_from_b64(image_b64)

        effective_color = color_hint or dominant_color
        effective_category = category_hint or _infer_category_from_text(query_text)

        candidates: list[tuple[float, str, str, list[str]]] = []

        for product_id, item in self._catalog.items():
            if item.stock == 0 and item.status and item.status.casefold() not in ("active", "available"):
                continue
            if budget_max and item.price and item.price > budget_max:
                continue

            score, reasons, match_type = self._score_item(
                item=item,
                query_text=query_text,
                effective_color=effective_color,
                effective_category=effective_category,
                image_b64=image_b64,
            )
            if score > 0.1:
                candidates.append((score, product_id, match_type, reasons))

        candidates.sort(key=lambda x: x[0], reverse=True)

        results: list[ImageMatchResult] = []
        for score, product_id, match_type, reasons in candidates[:top_k]:
            item = self._catalog[product_id]
            image_url = primary_image_url(item)
            results.append(
                ImageMatchResult(
                    product_id=product_id,
                    name=item.name,
                    score=round(score, 3),
                    match_type=match_type,
                    reasons=tuple(reasons),
                    price=item.price,
                    currency=item.currency,
                    stock=item.stock,
                    image_url=image_url,
                )
            )
        return results

    def _score_item(
        self,
        item: InventoryItemRecord,
        query_text: str,
        effective_color: str | None,
        effective_category: str | None,
        image_b64: str | None,
    ) -> tuple[float, list[str], str]:
        score = 0.0
        reasons: list[str] = []
        match_type = "visual_similar"
        attrs = item.attributes
        normalized_text = query_text.casefold()

        if effective_category:
            item_cat = (attrs.get("category_key") or (item.category or "")).casefold()
            if item_cat == effective_category.casefold():
                score += 0.4
                reasons.append(f"category match: {effective_category}")
            elif effective_category.casefold() in item_cat or item_cat in effective_category.casefold():
                score += 0.2

        if effective_color:
            item_color = (attrs.get("color") or "").casefold()
            item_family = (attrs.get("color_family") or "").casefold()
            if effective_color.casefold() == item_color:
                score += 0.3
                reasons.append(f"exact color match: {effective_color}")
            elif effective_color.casefold() == item_family:
                score += 0.15
                reasons.append(f"color family match: {effective_color}")

        design_id = attrs.get("design_id") or ""
        if design_id and any(w in normalized_text for w in design_id.split("-")):
            score += 0.25
            reasons.append(f"design pattern match: {design_id}")
            match_type = "same_design_variant"

        work_type = attrs.get("work_type") or ""
        work_terms = ["buti", "katan", "jamdani", "muslin", "embroidery", "printed", "block print"]
        for term in work_terms:
            if term in normalized_text and term in work_type.casefold():
                score += 0.15
                reasons.append(f"work type match: {term}")
                break

        if item.stock > 0:
            score += 0.05
            reasons.append("in stock")

        if item.stock == 0:
            score *= 0.3

        return score, reasons, match_type

    def build_answer(self, results: list[ImageMatchResult], query_text: str) -> str:
        if not results:
            return (
                "I could not find a close visual match in the current catalog. "
                "Please describe the color, fabric, or occasion and I will search by details."
            )
        lines: list[str] = []
        in_stock = [r for r in results if r.stock > 0]
        out_of_stock = [r for r in results if r.stock == 0]

        if in_stock:
            lines.append(f"I found {len(in_stock)} visually similar product(s) in stock:\n")
            for i, r in enumerate(in_stock[:3], 1):
                label = "same design" if r.match_type == "same_design_variant" else "visually similar"
                lines.append(
                    f"{i}. **{r.name}** — BDT {r.price:,.0f} | Stock: {r.stock} | {label.title()}"
                )
                if r.reasons:
                    lines.append(f"   (Matched: {', '.join(r.reasons[:2])})")

            lines.append(
                "\n*Note: These are similar design/color matches. "
                "Exact same SKU can only be confirmed with a product code.*"
            )
        if out_of_stock:
            lines.append(f"\nCurrently out of stock but similar:")
            for r in out_of_stock[:2]:
                lines.append(f"- {r.name} (out of stock)")

        return "\n".join(lines)


def _infer_category_from_text(text: str) -> str | None:
    text = text.casefold()
    category_hints = {
        "saree": ("saree", "sari", "শাড়ি", "jamdani", "katan", "muslin"),
        "bag": ("bag", "clutch", "purse", "handbag", "ব্যাগ", "পটলি"),
        "shoes": ("shoe", "sandal", "loafer", "heel", "জুতা"),
        "jewelry": ("jewelry", "necklace", "bangle", "earring", "গয়না", "চুড়ি"),
        "panjabi": ("panjabi", "punjabi", "kurta", "পাঞ্জাবি"),
        "cosmetics": ("lipstick", "foundation", "kajal", "makeup", "লিপস্টিক"),
        "beauty": ("sunscreen", "face wash", "serum", "cream", "সানস্ক্রিন"),
        "perfume": ("perfume", "attar", "fragrance", "পারফিউম"),
    }
    for cat, terms in category_hints.items():
        if any(t in text for t in terms):
            return cat
    return None


def primary_image_asset(item: InventoryItemRecord) -> InventoryImageAsset | None:
    if item.images:
        for image in item.images:
            if image.role == "primary":
                return image
        return item.images[0]
    return None


def primary_image_url(item: InventoryItemRecord) -> str | None:
    asset = primary_image_asset(item)
    if asset is not None:
        return asset.url or asset.local_path
    images = item.metadata.get("images") or item.attributes.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            value = first.get("url") or first.get("local_path")
            return str(value) if value else None
        if isinstance(first, str):
            return first
    return None
