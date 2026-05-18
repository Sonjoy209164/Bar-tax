"""Catalog-identity helpers.

One place to ask the catalog "what kind of identity does this product have?"
so the image matcher, decision policy, answer layer, and memory don't all
sprinkle `attrs.get("variant_group_id") or attrs.get("design_id") or ...`
patterns that drift out of sync.

These helpers accept either an `InventoryItemRecord` or an
`InventoryImageAsset` where the meaning is unambiguous.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.schemas import InventoryImageAsset, InventoryItemRecord


def image_can_confirm_exact(image_or_product: Any) -> bool:
    """True when the image evidence is strong enough to claim an exact SKU.

    Accepts an `InventoryImageAsset` or an `InventoryItemRecord` (uses its
    primary image asset). A demo/reference image can never anchor an exact
    claim — that's the single most important production safety rule.
    """
    image = _coerce_to_image(image_or_product)
    if image is None:
        return False
    return image.kind == "product_photo" and not image.is_reference


def product_variant_group(product: InventoryItemRecord | None) -> str | None:
    """The variant-group id used to group same-design / different-color SKUs.

    Falls back to `variant_group_name` and finally `design_id` so a partially
    populated catalog still groups predictably. Returns None when no identity
    signal exists at all.
    """
    if product is None:
        return None
    attrs = product.attributes or {}
    for key in ("variant_group_id", "variant_group_name", "design_id"):
        value = attrs.get(key)
        if value:
            return str(value).strip() or None
    return None


def product_design_id(product: InventoryItemRecord | None) -> str | None:
    """The design/pattern identity (color-independent)."""
    if product is None:
        return None
    attrs = product.attributes or {}
    value = attrs.get("design_id") or attrs.get("variant_group_id")
    return str(value).strip() if value else None


def product_category_key(product: InventoryItemRecord | None) -> str | None:
    """Lowercased category key — the safest signal for cross-category guards."""
    if product is None:
        return None
    attrs = product.attributes or {}
    key = attrs.get("category_key") or (product.category or "")
    key = (key or "").strip().casefold()
    return key or None


def product_color(product: InventoryItemRecord | None) -> str | None:
    """Concrete colour for this SKU (e.g. "olive")."""
    if product is None:
        return None
    attrs = product.attributes or {}
    value = attrs.get("color") or attrs.get("color_family")
    return str(value).strip() if value else None


def product_color_family(product: InventoryItemRecord | None) -> str | None:
    """Broader colour family (e.g. olive -> green)."""
    if product is None:
        return None
    attrs = product.attributes or {}
    value = attrs.get("color_family") or attrs.get("color")
    return str(value).strip() if value else None


_SIZE_TOKEN_RE = re.compile(r"^(?:[a-zA-Z]+|\d+)$")


def product_size_stock(product: InventoryItemRecord | None) -> dict[str, int]:
    """Per-size stock breakdown.

    Preferred source: the top-level `size_stock` field on
    `InventoryItemRecord` (e.g. `{"M": 2, "L": 1, "XL": 0}`). When only a
    comma-separated `attributes.size` string is present, fall back to listing
    each size with the total stock — the answer layer must then hedge using
    `product_size_stock_is_authoritative`.
    """
    if product is None:
        return {}
    top_level = getattr(product, "size_stock", None) or {}
    if isinstance(top_level, dict):
        cleaned: dict[str, int] = {}
        for label, count in top_level.items():
            key = str(label).strip().upper()
            if not key:
                continue
            try:
                cleaned[key] = max(0, int(count))
            except (TypeError, ValueError):
                continue
        if cleaned:
            return cleaned
    attrs = product.attributes or {}
    sizes_str = attrs.get("size") or attrs.get("size_options")
    if not sizes_str:
        return {}
    fallback: dict[str, int] = {}
    for token in str(sizes_str).split(","):
        size = token.strip().upper()
        if size and _SIZE_TOKEN_RE.match(size):
            fallback[size] = product.stock if product.stock else 0
    return fallback


def product_size_stock_is_authoritative(product: InventoryItemRecord | None) -> bool:
    """True only when the catalog actually has per-size counts."""
    if product is None:
        return False
    top_level = getattr(product, "size_stock", None)
    return isinstance(top_level, dict) and bool(top_level)


def find_variant_siblings(
    product_id: str,
    catalog: dict[str, InventoryItemRecord],
) -> list[InventoryItemRecord]:
    """Return every catalog item that shares this product's variant group."""
    primary = catalog.get(product_id)
    if primary is None:
        return []
    group = product_variant_group(primary)
    if not group:
        return [primary]
    target = _normalize(group)
    siblings: list[InventoryItemRecord] = []
    for item in catalog.values():
        candidate = product_variant_group(item)
        if candidate and _normalize(candidate) == target:
            siblings.append(item)
    siblings.sort(key=lambda item: (item.stock <= 0, product_color(item) or "", item.name.casefold()))
    return siblings


def _coerce_to_image(value: Any) -> InventoryImageAsset | None:
    if isinstance(value, InventoryImageAsset):
        return value
    if isinstance(value, InventoryItemRecord):
        images = value.images or []
        for image in images:
            if image.role == "primary":
                return image
        return images[0] if images else None
    return None


def _normalize(value: str | None) -> str:
    return (value or "").casefold().replace(" ", "-").replace("_", "-")
