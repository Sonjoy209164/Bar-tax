from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.core.schemas import InventoryItemRecord
from app.inventory.pos_sync import POSSyncEngine, SyncResult, _row_to_item


_SAMPLE_CSV = """\
product_id,sku,name,category,brand,price,currency,stock,status,tags,updated_at
saree-test-001,SAR-TEST-001,Test Red Saree,Saree,TestBrand,5000,BDT,3,Active,"saree,red",2026-05-09T00:00:00Z
saree-test-002,SAR-TEST-002,Test Blue Saree,Saree,TestBrand,4500,BDT,0,Active,"saree,blue",2026-05-09T00:00:00Z
"""

_SAMPLE_WEBHOOK = {
    "source": "pos",
    "event": "stock_updated",
    "items": [
        {
            "sku": "SAR-JMD-LOTUS-RED",
            "stock": 2,
            "price": 6800,
            "status": "Active",
            "updated_at": "2026-05-09T14:30:00+06:00",
        }
    ],
}


def _engine_with_temp_catalog() -> tuple[POSSyncEngine, Path]:
    tmpdir = tempfile.mkdtemp()
    catalog_path = Path(tmpdir) / "catalog.jsonl"
    engine = POSSyncEngine(catalog_path=catalog_path)
    return engine, catalog_path


def test_csv_import_inserts_new_items():
    engine, catalog_path = _engine_with_temp_catalog()
    result = engine.import_from_csv(_SAMPLE_CSV)
    assert result.inserted == 2
    assert result.skipped == 0
    assert len(result.errors) == 0
    assert catalog_path.exists()


def test_csv_import_loads_catalog_correctly():
    engine, catalog_path = _engine_with_temp_catalog()
    engine.import_from_csv(_SAMPLE_CSV)
    catalog = engine.load_catalog()
    assert "saree-test-001" in catalog
    assert catalog["saree-test-001"].name == "Test Red Saree"
    assert catalog["saree-test-001"].price == 5000.0
    assert catalog["saree-test-001"].stock == 3


def test_csv_import_detects_stock_change_on_second_run():
    engine, catalog_path = _engine_with_temp_catalog()
    engine.import_from_csv(_SAMPLE_CSV)

    updated_csv = _SAMPLE_CSV.replace(",3,Active", ",5,Active")
    result2 = engine.import_from_csv(updated_csv)
    assert result2.stock_changed >= 1


def test_csv_import_skips_rows_without_required_fields():
    bad_csv = "product_id,sku,name\n,NOSKU,No Name\nGOOD-001,GOOD-SKU,Good Product\n"
    engine, _ = _engine_with_temp_catalog()
    result = engine.import_from_csv(bad_csv)
    assert result.inserted == 1
    assert result.skipped >= 1


def test_webhook_import_updates_existing_stock():
    engine, catalog_path = _engine_with_temp_catalog()
    engine.import_from_csv(_SAMPLE_CSV)
    catalog = engine.load_catalog()
    item = list(catalog.values())[0]
    webhook = {
        "source": "pos",
        "event": "stock_updated",
        "items": [{"sku": item.sku, "stock": 10, "updated_at": "2026-05-09T00:00:00Z"}],
    }
    result = engine.import_from_webhook(webhook)
    assert result.stock_changed >= 1 or result.updated >= 1


def test_webhook_import_skips_unknown_sku():
    engine, catalog_path = _engine_with_temp_catalog()
    engine.import_from_csv(_SAMPLE_CSV)
    webhook = {
        "source": "pos",
        "event": "stock_updated",
        "items": [{"sku": "NONEXISTENT-SKU", "stock": 5}],
    }
    result = engine.import_from_webhook(webhook)
    assert result.skipped >= 1


def test_sync_status_returns_correct_counts():
    engine, catalog_path = _engine_with_temp_catalog()
    engine.import_from_csv(_SAMPLE_CSV)
    status = engine.get_sync_status()
    assert status["total_products"] == 2
    assert status["active_products"] >= 0
    assert status["out_of_stock"] >= 0


def test_row_to_item_creates_valid_record():
    row = {
        "product_id": "test-001",
        "sku": "TEST-001",
        "name": "Test Product",
        "category": "Saree",
        "brand": "TestBrand",
        "price": "5000",
        "currency": "BDT",
        "stock": "3",
        "status": "Active",
        "tags": "saree,red",
    }
    item = _row_to_item(row)
    assert item is not None
    assert item.product_id == "test-001"
    assert item.price == 5000.0
    assert item.stock == 3
    assert "saree" in item.tags


def test_row_to_item_returns_none_for_missing_required():
    row = {"sku": "TEST-001", "name": "Test"}
    item = _row_to_item(row)
    assert item is None


def test_sync_result_summary_text():
    result = SyncResult(inserted=2, updated=1, stock_changed=3, skipped=0, errors=[])
    summary = result.summary()
    assert "2 inserted" in summary
    assert "3 stock changes" in summary
