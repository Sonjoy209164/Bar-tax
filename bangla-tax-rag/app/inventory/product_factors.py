"""Product factor extraction for CIF-RAG.

This module exposes a deterministic factor view over catalog items. It is the
structured counterpart to visual embeddings: CLIP proposes visual neighbors,
while product factors explain which identity dimensions are being compared.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.schemas import InventoryItemRecord
from app.inventory.catalog_identity import (
    product_category_key,
    product_color,
    product_color_family,
    product_design_id,
    product_variant_group,
)


@dataclass(frozen=True)
class ProductFactor:
    label: str | None
    score: float
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score": self.score,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ProductFactorProfile:
    product_id: str
    image_id: str | None
    category_factor: ProductFactor
    design_factor: ProductFactor
    color_factor: ProductFactor
    shape_factor: ProductFactor
    texture_factor: ProductFactor
    text_factor: ProductFactor
    source_trust: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "image_id": self.image_id,
            "category_factor": self.category_factor.to_dict(),
            "design_factor": self.design_factor.to_dict(),
            "color_factor": self.color_factor.to_dict(),
            "shape_factor": self.shape_factor.to_dict(),
            "texture_factor": self.texture_factor.to_dict(),
            "text_factor": self.text_factor.to_dict(),
            "source_trust": self.source_trust,
        }


def factorize_product(item: InventoryItemRecord) -> ProductFactorProfile:
    attrs = item.attributes or {}
    image = _primary_image(item)
    design = product_design_id(item) or product_variant_group(item)
    category = product_category_key(item)
    color = product_color(item)
    color_family = product_color_family(item)
    shape = _first_present(attrs, "product_type", "neckline", "sleeve", "fit")
    texture = _first_present(attrs, "pattern_type", "work_type", "fabric", "style")
    text_terms = _text_terms(item, attrs)
    return ProductFactorProfile(
        product_id=item.product_id,
        image_id=image.image_id if image else None,
        category_factor=ProductFactor(category, _score(category), ("category_key", "category")),
        design_factor=ProductFactor(design, _score(design), ("design_id", "variant_group_id")),
        color_factor=ProductFactor(
            color,
            _score(color),
            tuple(key for key in ("color", "color_family") if attrs.get(key)) or ("color",),
        ),
        shape_factor=ProductFactor(shape, _score(shape), ("product_type", "neckline", "sleeve", "fit")),
        texture_factor=ProductFactor(texture, _score(texture), ("pattern_type", "work_type", "fabric", "style")),
        text_factor=ProductFactor(" ".join(text_terms[:16]) if text_terms else None, _score(text_terms), ("name", "tags", "visual_tags")),
        source_trust=_source_trust(image),
    )


def factorize_catalog(catalog: dict[str, InventoryItemRecord]) -> dict[str, ProductFactorProfile]:
    return {product_id: factorize_product(item) for product_id, item in catalog.items()}


def _first_present(attrs: dict[str, str], *keys: str) -> str | None:
    values = [str(attrs.get(key) or "").strip() for key in keys]
    return " ".join(value for value in values if value) or None


def _text_terms(item: InventoryItemRecord, attrs: dict[str, str]) -> list[str]:
    terms = [item.name, item.category or "", item.brand or ""]
    terms.extend(item.tags or [])
    terms.extend(str(value) for value in attrs.values() if value)
    if item.images:
        terms.extend(tag for image in item.images for tag in (image.visual_tags or []))
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        normalized = str(term).strip().casefold()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _score(value: Any) -> float:
    if isinstance(value, (list, tuple, set)):
        return 0.9 if value else 0.0
    return 0.9 if value else 0.0


def _primary_image(item: InventoryItemRecord):
    for image in item.images or []:
        if image.role == "primary":
            return image
    return item.images[0] if item.images else None


def _source_trust(image) -> str:
    if image is None:
        return "missing"
    if image.is_reference:
        return "reference_photo"
    return image.kind or "unknown"
