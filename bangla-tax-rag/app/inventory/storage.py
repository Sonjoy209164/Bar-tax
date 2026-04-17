from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from app.core.schemas import InventoryBusinessSignalRecord, InventoryItemRecord


InventoryStorageBackend = Literal["jsonl", "sqlite"]


class InventoryMirrorStore:
    """Persistence boundary for the mirrored inventory intelligence layer."""

    backend: str

    def load_catalog(self) -> dict[str, InventoryItemRecord]:
        raise NotImplementedError

    def persist_catalog(self, items: dict[str, InventoryItemRecord]) -> None:
        raise NotImplementedError

    def load_business_signals(self) -> dict[str, InventoryBusinessSignalRecord]:
        raise NotImplementedError

    def persist_business_signals(self, signals: dict[str, InventoryBusinessSignalRecord]) -> None:
        raise NotImplementedError

    def describe(self) -> dict[str, str]:
        raise NotImplementedError


class JsonlInventoryMirrorStore(InventoryMirrorStore):
    backend = "jsonl"

    def __init__(self, *, catalog_path: str, business_signal_path: str) -> None:
        self.catalog_path = Path(catalog_path)
        self.business_signal_path = Path(business_signal_path)

    def load_catalog(self) -> dict[str, InventoryItemRecord]:
        if not self.catalog_path.exists():
            return {}
        items: dict[str, InventoryItemRecord] = {}
        with self.catalog_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                item = InventoryItemRecord.model_validate_json(stripped)
                items[item.product_id] = item
        return items

    def persist_catalog(self, items: dict[str, InventoryItemRecord]) -> None:
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        with self.catalog_path.open("w", encoding="utf-8") as handle:
            for item in sorted(items.values(), key=lambda value: ((value.updated_at or ""), value.name.casefold())):
                handle.write(item.model_dump_json())
                handle.write("\n")

    def load_business_signals(self) -> dict[str, InventoryBusinessSignalRecord]:
        if not self.business_signal_path.exists():
            return {}
        signals: dict[str, InventoryBusinessSignalRecord] = {}
        with self.business_signal_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                signal = InventoryBusinessSignalRecord.model_validate_json(stripped)
                signals[signal.product_id] = signal
        return signals

    def persist_business_signals(self, signals: dict[str, InventoryBusinessSignalRecord]) -> None:
        self.business_signal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.business_signal_path.open("w", encoding="utf-8") as handle:
            for signal in sorted(
                signals.values(),
                key=lambda value: (
                    value.updated_at or value.period_end or value.inventory_snapshot_at or "",
                    value.period_end or "",
                    value.product_id,
                ),
            ):
                handle.write(signal.model_dump_json())
                handle.write("\n")

    def describe(self) -> dict[str, str]:
        return {
            "backend": self.backend,
            "catalog_path": str(self.catalog_path),
            "business_signal_path": str(self.business_signal_path),
        }


class SqliteInventoryMirrorStore(InventoryMirrorStore):
    backend = "sqlite"

    def __init__(self, *, sqlite_path: str) -> None:
        self.sqlite_path = Path(sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def load_catalog(self) -> dict[str, InventoryItemRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM inventory_catalog").fetchall()
        items: dict[str, InventoryItemRecord] = {}
        for (payload,) in rows:
            item = InventoryItemRecord.model_validate_json(payload)
            items[item.product_id] = item
        return items

    def persist_catalog(self, items: dict[str, InventoryItemRecord]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM inventory_catalog")
            connection.executemany(
                """
                INSERT INTO inventory_catalog(product_id, updated_at, include_in_rag, payload)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        item.product_id,
                        item.updated_at,
                        1 if item.include_in_rag else 0,
                        item.model_dump_json(),
                    )
                    for item in sorted(items.values(), key=lambda value: ((value.updated_at or ""), value.name.casefold()))
                ],
            )

    def load_business_signals(self) -> dict[str, InventoryBusinessSignalRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM inventory_business_signals").fetchall()
        signals: dict[str, InventoryBusinessSignalRecord] = {}
        for (payload,) in rows:
            signal = InventoryBusinessSignalRecord.model_validate_json(payload)
            signals[signal.product_id] = signal
        return signals

    def persist_business_signals(self, signals: dict[str, InventoryBusinessSignalRecord]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM inventory_business_signals")
            connection.executemany(
                """
                INSERT INTO inventory_business_signals(product_id, updated_at, period_end, payload)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        signal.product_id,
                        signal.updated_at,
                        signal.period_end,
                        signal.model_dump_json(),
                    )
                    for signal in sorted(
                        signals.values(),
                        key=lambda value: (
                            value.updated_at or value.period_end or value.inventory_snapshot_at or "",
                            value.period_end or "",
                            value.product_id,
                        ),
                    )
                ],
            )

    def describe(self) -> dict[str, str]:
        return {
            "backend": self.backend,
            "sqlite_path": str(self.sqlite_path),
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory_catalog (
                    product_id TEXT PRIMARY KEY,
                    updated_at TEXT,
                    include_in_rag INTEGER NOT NULL DEFAULT 1,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory_business_signals (
                    product_id TEXT PRIMARY KEY,
                    updated_at TEXT,
                    period_end TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_inventory_catalog_updated_at ON inventory_catalog(updated_at)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_inventory_business_signals_updated_at ON inventory_business_signals(updated_at)"
            )


def build_inventory_mirror_store(
    *,
    backend: str,
    catalog_path: str,
    business_signal_path: str,
    sqlite_path: str,
) -> InventoryMirrorStore:
    normalized_backend = backend.strip().casefold()
    if normalized_backend == "jsonl":
        return JsonlInventoryMirrorStore(catalog_path=catalog_path, business_signal_path=business_signal_path)
    if normalized_backend == "sqlite":
        return SqliteInventoryMirrorStore(sqlite_path=sqlite_path)
    raise ValueError("inventory storage backend must be either 'jsonl' or 'sqlite'")
