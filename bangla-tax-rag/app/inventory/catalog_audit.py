from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path("data/inventory/catalog.jsonl")

_REQUIRED_ATTRIBUTES = ("category_key", "color", "fabric")
_RECOMMENDED_ATTRIBUTES = ("work_type", "design_id", "size", "occasion")
_IMAGE_IDENTITY_ATTRIBUTES = ("design_id", "variant_group_id", "color", "color_family")
_REQUIRED_FIELDS = ("sku", "name", "price", "stock", "category")


@dataclass
class AuditIssue:
    product_id: str
    name: str
    issue_type: str
    detail: str


@dataclass
class CatalogAuditReport:
    total_products: int = 0
    active_products: int = 0
    rag_enabled: int = 0
    out_of_stock: int = 0
    issues: list[AuditIssue] = field(default_factory=list)
    completeness_score: float = 0.0
    attribute_coverage: dict[str, int] = field(default_factory=dict)
    category_counts: dict[str, int] = field(default_factory=dict)
    brand_counts: dict[str, int] = field(default_factory=dict)
    price_range: dict[str, float] = field(default_factory=dict)
    enrichment_candidates: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Catalog Audit — {self.total_products} products",
            f"  Active: {self.active_products}  |  RAG-enabled: {self.rag_enabled}  |  Out-of-stock: {self.out_of_stock}",
            f"  Completeness score: {self.completeness_score:.0%}",
            f"  Issues found: {len(self.issues)}",
        ]
        if self.attribute_coverage:
            lines.append("  Attribute coverage:")
            for attr, count in sorted(self.attribute_coverage.items()):
                pct = count / self.total_products if self.total_products else 0
                lines.append(f"    {attr}: {count}/{self.total_products} ({pct:.0%})")
        if self.issues:
            lines.append("  Top issues (first 10):")
            for issue in self.issues[:10]:
                lines.append(f"    [{issue.issue_type}] {issue.product_id} — {issue.detail}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_products": self.total_products,
            "active_products": self.active_products,
            "rag_enabled": self.rag_enabled,
            "out_of_stock": self.out_of_stock,
            "completeness_score": round(self.completeness_score, 4),
            "issues_count": len(self.issues),
            "issues": [
                {"product_id": i.product_id, "name": i.name, "issue_type": i.issue_type, "detail": i.detail}
                for i in self.issues
            ],
            "attribute_coverage": self.attribute_coverage,
            "category_counts": self.category_counts,
            "brand_counts": self.brand_counts,
            "price_range": self.price_range,
            "enrichment_candidates": self.enrichment_candidates[:20],
        }


def audit_catalog(catalog_path: Path = _CATALOG_PATH) -> CatalogAuditReport:
    report = CatalogAuditReport()

    if not catalog_path.exists():
        return report

    raw_items: list[dict[str, Any]] = []
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            try:
                raw_items.append(json.loads(stripped))
            except json.JSONDecodeError:
                pass

    report.total_products = len(raw_items)
    if not raw_items:
        return report

    attr_counts: dict[str, int] = {
        a: 0
        for a in _REQUIRED_ATTRIBUTES + _RECOMMENDED_ATTRIBUTES + _IMAGE_IDENTITY_ATTRIBUTES
    }
    prices: list[float] = []

    for item in raw_items:
        pid = item.get("product_id", "unknown")
        name = item.get("name", "")
        status = (item.get("status") or "").casefold()
        attrs: dict[str, str] = item.get("attributes") or {}

        if status not in ("archived", "draft", "inactive"):
            report.active_products += 1
        if item.get("include_in_rag", True):
            report.rag_enabled += 1
        if (item.get("stock") or 0) == 0:
            report.out_of_stock += 1

        # Required field checks
        for fld in _REQUIRED_FIELDS:
            if not item.get(fld):
                report.issues.append(AuditIssue(pid, name, "missing_required_field", f"'{fld}' is empty"))

        price = item.get("price")
        if price is not None:
            if float(price) == 0.0:
                report.issues.append(AuditIssue(pid, name, "zero_price", "price is 0"))
            else:
                prices.append(float(price))

        stock = item.get("stock")
        if stock is not None and int(stock) < 0:
            report.issues.append(AuditIssue(pid, name, "negative_stock", f"stock={stock}"))

        # Required attribute checks
        for attr in _REQUIRED_ATTRIBUTES:
            if attrs.get(attr):
                attr_counts[attr] += 1
            else:
                report.issues.append(AuditIssue(pid, name, "missing_required_attr", f"attributes['{attr}'] missing"))

        # Recommended attribute checks
        for attr in _RECOMMENDED_ATTRIBUTES:
            if attrs.get(attr):
                attr_counts[attr] += 1
            else:
                report.issues.append(AuditIssue(pid, name, "missing_recommended_attr", f"attributes['{attr}'] missing — search quality degraded"))

        images = item.get("images") or []
        if images:
            for attr in _IMAGE_IDENTITY_ATTRIBUTES:
                if attrs.get(attr):
                    if attr not in _REQUIRED_ATTRIBUTES and attr not in _RECOMMENDED_ATTRIBUTES:
                        attr_counts[attr] += 1
                else:
                    report.issues.append(
                        AuditIssue(
                            pid,
                            name,
                            "missing_image_identity_attr",
                            f"visual product missing attributes['{attr}'] — image search confidence degraded",
                        )
                    )
            if all(bool(image.get("is_reference")) for image in images):
                report.issues.append(
                    AuditIssue(
                        pid,
                        name,
                        "reference_image_only",
                        "all images are reference/demo images; exact visual match must be disabled",
                    )
                )
            for image in images:
                if not image.get("image_id"):
                    report.issues.append(AuditIssue(pid, name, "missing_image_id", "image asset missing image_id"))
                if not image.get("local_path") and not image.get("url"):
                    report.issues.append(AuditIssue(pid, name, "missing_image_source", "image asset missing local_path/url"))
                if image.get("role") not in {"primary", "alternate", "detail", "reference"}:
                    report.issues.append(AuditIssue(pid, name, "invalid_image_role", f"invalid image role: {image.get('role')}"))
        else:
            report.issues.append(
                AuditIssue(
                    pid,
                    name,
                    "missing_image_asset",
                    "product has no image asset; screenshot search cannot match it",
                )
            )

        # Category/brand counts
        cat = (item.get("category") or "").strip()
        if cat:
            report.category_counts[cat] = report.category_counts.get(cat, 0) + 1

        brand = (item.get("brand") or "").strip()
        if brand:
            report.brand_counts[brand] = report.brand_counts.get(brand, 0) + 1

        # Enrichment candidates: items missing design_id or work_type with enough name+description to auto-fill
        if not attrs.get("design_id") or not attrs.get("work_type"):
            desc = (item.get("short_description") or item.get("full_description") or "")
            if len(name) >= 5 or len(desc) >= 10:
                report.enrichment_candidates.append({
                    "product_id": pid,
                    "name": name,
                    "description": desc[:120],
                    "missing": [a for a in ("design_id", "work_type", "color", "fabric") if not attrs.get(a)],
                })

    report.attribute_coverage = attr_counts

    if prices:
        report.price_range = {"min": min(prices), "max": max(prices), "avg": round(sum(prices) / len(prices), 2)}

    # Completeness: each product scored against all checked attributes
    total_checks = report.total_products * (len(_REQUIRED_FIELDS) + len(_REQUIRED_ATTRIBUTES) + len(_RECOMMENDED_ATTRIBUTES))
    total_issues = len([i for i in report.issues if i.issue_type != "missing_recommended_attr"])
    report.completeness_score = max(0.0, 1.0 - (total_issues / total_checks)) if total_checks else 0.0

    return report


def enrich_item_attributes(item: dict[str, Any]) -> dict[str, str]:
    """
    Rule-based attribute enrichment from product name + description.
    Returns a dict of suggested attribute values (not written automatically —
    caller decides whether to apply).
    For production: replace the rule stubs here with an LLM call.
    """
    suggestions: dict[str, str] = {}
    name_lower = (item.get("name") or "").casefold()
    desc_lower = (item.get("short_description") or item.get("full_description") or "").casefold()
    text = name_lower + " " + desc_lower

    # Fabric hints
    fabric_hints = {
        "jamdani": "jamdani", "katan": "katan", "muslin": "muslin", "silk": "silk",
        "cotton": "cotton", "linen": "linen", "georgette": "georgette", "chiffon": "chiffon",
        "denim": "denim", "velvet": "velvet",
    }
    for hint, fabric in fabric_hints.items():
        if hint in text:
            suggestions["fabric"] = fabric
            break

    # Work type hints
    work_hints = {
        "zari": "zari", "meena": "meena", "embroid": "embroidery", "block print": "block_print",
        "buti": "buti", "nakshi": "nakshi", "printed": "printed", "plain": "plain",
    }
    for hint, work in work_hints.items():
        if hint in text:
            suggestions["work_type"] = work
            break

    # Color hints
    color_hints = {
        "red": "red", "blue": "blue", "green": "green", "black": "black", "white": "white",
        "navy": "navy", "gold": "gold", "pink": "pink", "purple": "purple", "orange": "orange",
        "yellow": "yellow", "grey": "grey", "gray": "grey", "beige": "beige", "cream": "cream",
        "maroon": "maroon", "royal": "blue",
    }
    for hint, color in color_hints.items():
        if hint in text:
            suggestions["color"] = color
            break

    # Category key hints
    cat_hints = {
        "saree": "saree", "panjabi": "panjabi", "punjabi": "panjabi", "kurti": "kurti",
        "bag": "bag", "shoe": "shoe", "sandal": "shoe", "loafer": "shoe",
        "jewel": "jewelry", "necklace": "jewelry", "earring": "jewelry",
        "sunscreen": "cosmetics", "serum": "cosmetics", "moisturizer": "cosmetics",
        "fragrance": "fragrance", "perfume": "fragrance",
    }
    for hint, cat in cat_hints.items():
        if hint in text:
            suggestions["category_key"] = cat
            break

    return suggestions
