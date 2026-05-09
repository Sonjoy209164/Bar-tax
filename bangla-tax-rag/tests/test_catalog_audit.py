"""Tests for catalog_audit module."""
import json
from pathlib import Path

import pytest

from app.inventory.catalog_audit import AuditIssue, CatalogAuditReport, audit_catalog, enrich_item_attributes


@pytest.fixture()
def catalog_jsonl(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.jsonl"
    items = [
        {
            "product_id": "p1",
            "sku": "SKU001",
            "name": "Red Jamdani Saree",
            "price": 5000,
            "stock": 3,
            "category": "Saree",
            "include_in_rag": True,
            "attributes": {"category_key": "saree", "color": "red", "fabric": "jamdani"},
        },
        {
            "product_id": "p2",
            "sku": "SKU002",
            "name": "Missing Price Panjabi",
            "price": 0,
            "stock": 5,
            "category": "Panjabi",
            "include_in_rag": True,
            "attributes": {"category_key": "panjabi"},
        },
        {
            "product_id": "p3",
            "sku": "SKU003",
            "name": "No Category Item",
            "price": 1200,
            "stock": 0,
            "category": "",
            "include_in_rag": False,
            "attributes": {},
        },
    ]
    path.write_text("\n".join(json.dumps(i) for i in items), encoding="utf-8")
    return path


def test_audit_returns_report(catalog_jsonl: Path) -> None:
    report = audit_catalog(catalog_jsonl)
    assert isinstance(report, CatalogAuditReport)
    assert report.total_products == 3


def test_audit_detects_zero_price(catalog_jsonl: Path) -> None:
    report = audit_catalog(catalog_jsonl)
    zero_price_issues = [i for i in report.issues if i.issue_type == "zero_price"]
    assert any(i.product_id == "p2" for i in zero_price_issues)


def test_audit_detects_out_of_stock(catalog_jsonl: Path) -> None:
    report = audit_catalog(catalog_jsonl)
    assert report.out_of_stock >= 1


def test_audit_rag_enabled_count(catalog_jsonl: Path) -> None:
    report = audit_catalog(catalog_jsonl)
    # p1 and p2 have include_in_rag=True; p3 has False
    # Note: audit_catalog uses item.get("include_in_rag", True) — default True when absent
    assert report.rag_enabled >= 2


def test_audit_completeness_score_between_0_and_1(catalog_jsonl: Path) -> None:
    report = audit_catalog(catalog_jsonl)
    assert 0.0 <= report.completeness_score <= 1.0


def test_audit_missing_catalog_returns_empty(tmp_path: Path) -> None:
    report = audit_catalog(tmp_path / "nonexistent.jsonl")
    assert report.total_products == 0
    assert report.issues == []


def test_enrich_item_attributes_fabric_from_name() -> None:
    item = {"name": "Beautiful Jamdani Saree", "short_description": "hand woven", "attributes": {}}
    suggestions = enrich_item_attributes(item)
    assert "fabric" in suggestions or "category_key" in suggestions


def test_enrich_item_attributes_no_crash_on_empty() -> None:
    suggestions = enrich_item_attributes({"name": "", "attributes": {}})
    assert isinstance(suggestions, dict)
