from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.schemas import InventoryItemRecord


logger = logging.getLogger(__name__)

_SYNC_LOG_PATH = Path("data/inventory/sync_audit.jsonl")
_CATALOG_PATH = Path("data/inventory/catalog.jsonl")


@dataclass
class SyncResult:
    inserted: int = 0
    updated: int = 0
    stock_changed: int = 0
    deactivated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "stock_changed": self.stock_changed,
            "deactivated": self.deactivated,
            "skipped": self.skipped,
            "errors": self.errors,
            "timestamp": self.timestamp,
        }

    def summary(self) -> str:
        return (
            f"Sync completed: {self.inserted} inserted, {self.updated} updated, "
            f"{self.stock_changed} stock changes, {self.deactivated} deactivated, "
            f"{self.skipped} skipped."
        )


class POSSyncEngine:
    """Handles CSV import, JSON webhook import, and incremental catalog updates."""

    def __init__(self, catalog_path: str | Path | None = None) -> None:
        self._catalog_path = Path(catalog_path) if catalog_path else _CATALOG_PATH

    def load_catalog(self) -> dict[str, InventoryItemRecord]:
        items: dict[str, InventoryItemRecord] = {}
        if not self._catalog_path.exists():
            return items
        for line in self._catalog_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = InventoryItemRecord.model_validate_json(stripped)
                items[item.product_id] = item
            except Exception as exc:
                logger.warning("Catalog parse error: %s", exc)
        return items

    def persist_catalog(self, items: dict[str, InventoryItemRecord]) -> None:
        self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
        with self._catalog_path.open("w", encoding="utf-8") as handle:
            for item in sorted(items.values(), key=lambda v: v.name.casefold()):
                handle.write(item.model_dump_json())
                handle.write("\n")

    def import_from_csv(self, csv_text: str) -> SyncResult:
        result = SyncResult()
        catalog = self.load_catalog()

        try:
            reader = csv.DictReader(io.StringIO(csv_text))
        except Exception as exc:
            result.errors.append(f"CSV parse failed: {exc}")
            _log_sync("csv", result)
            return result

        for row_num, row in enumerate(reader, 1):
            try:
                item = _row_to_item(row)
                if item is None:
                    result.skipped += 1
                    continue
                existing = catalog.get(item.product_id)
                if existing is None:
                    catalog[item.product_id] = item
                    result.inserted += 1
                else:
                    changed = False
                    if existing.stock != item.stock:
                        result.stock_changed += 1
                        changed = True
                    if existing.price != item.price or existing.status != item.status:
                        changed = True
                    if changed:
                        catalog[item.product_id] = item
                        result.updated += 1
                    else:
                        result.skipped += 1
            except Exception as exc:
                result.errors.append(f"Row {row_num}: {exc}")

        self.persist_catalog(catalog)
        _log_sync("csv", result)
        return result

    def import_from_webhook(self, payload: dict[str, Any]) -> SyncResult:
        result = SyncResult()
        catalog = self.load_catalog()

        items_data = payload.get("items", [])
        event = payload.get("event", "unknown")

        for item_data in items_data:
            try:
                sku = item_data.get("sku") or ""
                if not sku:
                    result.skipped += 1
                    continue

                existing_by_sku = {v.sku: v for v in catalog.values()}
                existing = existing_by_sku.get(sku)

                if existing is None:
                    result.skipped += 1
                    result.errors.append(f"SKU not found in catalog: {sku}")
                    continue

                old_stock = existing.stock
                new_data = existing.model_dump()

                if "stock" in item_data:
                    new_data["stock"] = int(item_data["stock"])
                if "price" in item_data:
                    new_data["price"] = float(item_data["price"])
                if "status" in item_data:
                    new_data["status"] = item_data["status"]
                if "updated_at" in item_data:
                    new_data["updated_at"] = item_data["updated_at"]
                else:
                    new_data["updated_at"] = datetime.now(timezone.utc).isoformat()

                updated_item = InventoryItemRecord.model_validate(new_data)
                catalog[existing.product_id] = updated_item

                if event == "stock_updated" or old_stock != updated_item.stock:
                    result.stock_changed += 1
                else:
                    result.updated += 1

            except Exception as exc:
                result.errors.append(f"Webhook item error: {exc}")

        self.persist_catalog(catalog)
        _log_sync("webhook", result)
        return result

    def get_sync_status(self) -> dict[str, Any]:
        catalog = self.load_catalog()
        active = sum(1 for v in catalog.values() if (v.status or "").casefold() == "active")
        out_of_stock = sum(1 for v in catalog.values() if v.stock == 0)
        last_sync: str | None = None

        if _SYNC_LOG_PATH.exists():
            lines = [l.strip() for l in _SYNC_LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
            if lines:
                try:
                    last_entry = json.loads(lines[-1])
                    last_sync = last_entry.get("timestamp")
                except (json.JSONDecodeError, KeyError):
                    pass

        return {
            "total_products": len(catalog),
            "active_products": active,
            "out_of_stock": out_of_stock,
            "last_sync": last_sync or "never",
        }


def _row_to_item(row: dict[str, str]) -> InventoryItemRecord | None:
    product_id = row.get("product_id") or row.get("id") or ""
    sku = row.get("sku") or row.get("SKU") or ""
    name = row.get("name") or row.get("product_name") or ""

    if not product_id or not sku or not name:
        return None

    try:
        price = float(row.get("price") or 0)
    except ValueError:
        price = 0.0

    try:
        stock = int(row.get("stock") or row.get("quantity") or 0)
    except ValueError:
        stock = 0

    tags_raw = row.get("tags") or ""
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    attributes: dict[str, str] = {}
    for key in ("category_key", "color", "color_family", "size", "fabric", "brand", "occasion"):
        val = row.get(key) or ""
        if val:
            attributes[key] = val

    return InventoryItemRecord(
        product_id=product_id,
        sku=sku,
        name=name,
        category=row.get("category") or None,
        brand=row.get("brand") or None,
        price=price,
        currency=row.get("currency") or "BDT",
        stock=stock,
        status=row.get("status") or "Active",
        tags=tags,
        attributes=attributes,
        include_in_rag=True,
        updated_at=row.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    )


def _log_sync(source: str, result: SyncResult) -> None:
    _SYNC_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"source": source, **result.to_dict()}
    with _SYNC_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False))
        handle.write("\n")
