"""Product factor graph for CIF-RAG.

The graph makes commerce identity explicit: products are connected to design,
variant group, color, size stock, image trust, and business state. It is a
lightweight in-memory graph over the existing catalog JSONL records, designed
for decision and evaluation logic rather than graph-database scale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.schemas import InventoryImageAsset, InventoryItemRecord
from app.inventory.catalog_identity import (
    image_can_confirm_exact,
    product_category_key,
    product_color,
    product_color_family,
    product_design_id,
    product_size_stock,
    product_size_stock_is_authoritative,
    product_variant_group,
)


@dataclass(frozen=True)
class ProductFactorNode:
    product_id: str
    sku: str
    name: str
    category_key: str | None
    design_id: str | None
    variant_group_id: str | None
    color: str | None
    color_family: str | None
    stock: int
    status: str | None
    price: float | None
    currency: str
    size_stock: dict[str, int]
    size_stock_authoritative: bool
    image_id: str | None
    image_kind: str | None
    image_is_reference: bool
    image_trust_level: str
    can_confirm_exact: bool
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SizeAvailability:
    product_id: str
    size: str
    known: bool
    available: bool
    stock: int | None
    reason: str


@dataclass(frozen=True)
class ProductEvidence:
    product_id: str
    identity: dict[str, Any]
    business_state: dict[str, Any]
    image_evidence: dict[str, Any]
    variant_siblings: list[str]
    available_colors: list[str]


class ProductFactorGraph:
    """Query product identity and business facts as graph relationships."""

    def __init__(self, catalog: dict[str, InventoryItemRecord]) -> None:
        self.catalog = catalog
        self.nodes = {
            product_id: self._node_from_item(item)
            for product_id, item in catalog.items()
        }
        self._by_variant_group: dict[str, list[str]] = {}
        self._by_design: dict[str, list[str]] = {}
        self._by_category: dict[str, list[str]] = {}
        for node in self.nodes.values():
            if node.variant_group_id:
                self._by_variant_group.setdefault(_normalize(node.variant_group_id), []).append(node.product_id)
            if node.design_id:
                self._by_design.setdefault(_normalize(node.design_id), []).append(node.product_id)
            if node.category_key:
                self._by_category.setdefault(_normalize(node.category_key), []).append(node.product_id)
        for index in (self._by_variant_group, self._by_design, self._by_category):
            for product_ids in index.values():
                product_ids.sort(key=self._sort_key)

    @classmethod
    def from_catalog(cls, catalog: dict[str, InventoryItemRecord]) -> "ProductFactorGraph":
        return cls(catalog)

    def product(self, product_id: str | None) -> ProductFactorNode | None:
        if not product_id:
            return None
        return self.nodes.get(product_id)

    def same_design_siblings(self, product_id: str | None, *, include_self: bool = True) -> list[ProductFactorNode]:
        node = self.product(product_id)
        if node is None:
            return []
        keys = [
            _normalize(node.variant_group_id),
            _normalize(node.design_id),
        ]
        product_ids: list[str] = []
        seen: set[str] = set()
        for key in keys:
            if not key:
                continue
            for candidate in self._by_variant_group.get(key, []) + self._by_design.get(key, []):
                if candidate in seen:
                    continue
                if not include_self and candidate == product_id:
                    continue
                seen.add(candidate)
                product_ids.append(candidate)
        if not product_ids and include_self:
            product_ids = [product_id]
        return [self.nodes[pid] for pid in product_ids if pid in self.nodes]

    def color_variants(self, product_id: str | None) -> dict[str, list[ProductFactorNode]]:
        variants: dict[str, list[ProductFactorNode]] = {}
        for node in self.same_design_siblings(product_id):
            color = node.color or node.color_family
            if not color:
                continue
            variants.setdefault(color.casefold(), []).append(node)
        return variants

    def available_colors(self, product_id: str | None, *, in_stock_only: bool = False) -> list[str]:
        colors: list[str] = []
        for node in self.same_design_siblings(product_id):
            if in_stock_only and node.stock <= 0:
                continue
            color = node.color or node.color_family
            if color and color not in colors:
                colors.append(color)
        return colors

    def find_color_variant(self, product_id: str | None, requested_color: str | None) -> list[ProductFactorNode]:
        if not requested_color:
            return []
        wanted = _normalize_color(requested_color)
        matches: list[ProductFactorNode] = []
        for node in self.same_design_siblings(product_id):
            candidates = {_normalize_color(node.color), _normalize_color(node.color_family)}
            if wanted in candidates:
                matches.append(node)
        return matches

    def size_availability(self, product_id: str | None, requested_size: str | None) -> SizeAvailability | None:
        node = self.product(product_id)
        if node is None or not requested_size:
            return None
        size = requested_size.strip().upper()
        if not node.size_stock_authoritative:
            if node.size_stock and size in node.size_stock:
                stock = node.size_stock[size]
                return SizeAvailability(
                    product_id=node.product_id,
                    size=size,
                    known=False,
                    available=stock > 0,
                    stock=stock,
                    reason="size listed but per-size stock is not authoritative",
                )
            return SizeAvailability(
                product_id=node.product_id,
                size=size,
                known=False,
                available=False,
                stock=None,
                reason="per-size stock missing",
            )
        stock = node.size_stock.get(size)
        if stock is None:
            return SizeAvailability(
                product_id=node.product_id,
                size=size,
                known=True,
                available=False,
                stock=0,
                reason="size not present in authoritative size_stock",
            )
        return SizeAvailability(
            product_id=node.product_id,
            size=size,
            known=True,
            available=stock > 0,
            stock=stock,
            reason="authoritative size_stock checked",
        )

    def can_claim_same_design(self, left_product_id: str | None, right_product_id: str | None) -> bool:
        left = self.product(left_product_id)
        right = self.product(right_product_id)
        if left is None or right is None:
            return False
        left_keys = {_normalize(left.variant_group_id), _normalize(left.design_id)} - {""}
        right_keys = {_normalize(right.variant_group_id), _normalize(right.design_id)} - {""}
        return bool(left_keys & right_keys)

    def can_claim_exact(self, product_id: str | None) -> bool:
        node = self.product(product_id)
        return bool(node and node.can_confirm_exact)

    def evidence_for_product(self, product_id: str | None) -> ProductEvidence | None:
        node = self.product(product_id)
        if node is None:
            return None
        siblings = self.same_design_siblings(product_id)
        return ProductEvidence(
            product_id=node.product_id,
            identity={
                "category_key": node.category_key,
                "design_id": node.design_id,
                "variant_group_id": node.variant_group_id,
                "color": node.color,
                "color_family": node.color_family,
            },
            business_state={
                "stock": node.stock,
                "status": node.status,
                "price": node.price,
                "currency": node.currency,
                "size_stock": node.size_stock,
                "size_stock_authoritative": node.size_stock_authoritative,
            },
            image_evidence={
                "image_id": node.image_id,
                "image_kind": node.image_kind,
                "is_reference": node.image_is_reference,
                "trust_level": node.image_trust_level,
                "can_confirm_exact": node.can_confirm_exact,
            },
            variant_siblings=[sibling.product_id for sibling in siblings if sibling.product_id != node.product_id],
            available_colors=self.available_colors(product_id),
        )

    def trace_for_product(self, product_id: str | None) -> dict[str, Any]:
        evidence = self.evidence_for_product(product_id)
        if evidence is None:
            return {"product_id": product_id, "found": False}
        return {
            "product_id": evidence.product_id,
            "found": True,
            "identity": evidence.identity,
            "business_state": evidence.business_state,
            "image_evidence": evidence.image_evidence,
            "variant_siblings": evidence.variant_siblings,
            "available_colors": evidence.available_colors,
        }

    def _node_from_item(self, item: InventoryItemRecord) -> ProductFactorNode:
        image = _primary_image(item)
        image_trust_level = _image_trust_level(image)
        return ProductFactorNode(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            category_key=product_category_key(item),
            design_id=product_design_id(item),
            variant_group_id=product_variant_group(item),
            color=product_color(item),
            color_family=product_color_family(item),
            stock=item.stock,
            status=item.status,
            price=item.price,
            currency=item.currency,
            size_stock=product_size_stock(item),
            size_stock_authoritative=product_size_stock_is_authoritative(item),
            image_id=image.image_id if image else None,
            image_kind=image.kind if image else None,
            image_is_reference=bool(image.is_reference) if image else False,
            image_trust_level=image_trust_level,
            can_confirm_exact=image_can_confirm_exact(item),
            attributes=dict(item.attributes or {}),
        )

    def _sort_key(self, product_id: str) -> tuple[bool, str, str]:
        node = self.nodes[product_id]
        return (node.stock <= 0, node.color or "", node.name.casefold())


def _primary_image(item: InventoryItemRecord) -> InventoryImageAsset | None:
    for image in item.images or []:
        if image.role == "primary":
            return image
    return item.images[0] if item.images else None


def _image_trust_level(image: InventoryImageAsset | None) -> str:
    if image is None:
        return "missing"
    if image.is_reference:
        return "reference_photo"
    if image.kind:
        return image.kind
    return "unknown"


def _normalize(value: str | None) -> str:
    return (value or "").strip().casefold().replace(" ", "-").replace("_", "-")


def _normalize_color(value: str | None) -> str:
    value = (value or "").strip().casefold()
    aliases = {
        "nil": "blue",
        "navy": "blue",
        "royal blue": "blue",
        "shada": "white",
        "off white": "white",
        "kalo": "black",
        "sobuj": "green",
        "olive": "green",
        "bottle green": "green",
        "dhushor": "grey",
        "gray": "grey",
    }
    return aliases.get(value, value)
