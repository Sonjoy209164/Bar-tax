from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_WAITLIST_PATH = Path("data/inventory/waitlist.jsonl")

WAITLIST_PHRASES = (
    "notify me", "let me know", "back in stock", "restock",
    "stock asle bolben", "stock ashle janaben", "stock e asle",
    "out of stock notif", "waitlist", "interested",
    "stock hobe", "কবে আসবে", "স্টক হলে জানাবেন",
)


@dataclass
class WaitlistEntry:
    session_id: str
    product_id: str
    product_name: str
    phone: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notified: bool = False
    notified_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "phone": self.phone,
            "created_at": self.created_at,
            "notified": self.notified,
            "notified_at": self.notified_at,
        }


class WaitlistManager:

    def add(self, session_id: str, product_id: str, product_name: str, phone: str | None = None) -> WaitlistEntry:
        entry = WaitlistEntry(
            session_id=session_id,
            product_id=product_id,
            product_name=product_name,
            phone=phone,
        )
        _WAITLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _WAITLIST_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return entry

    def get_waitlist(self, product_id: str) -> list[WaitlistEntry]:
        entries: list[WaitlistEntry] = []
        if not _WAITLIST_PATH.exists():
            return entries
        for line in _WAITLIST_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("product_id") == product_id and not data.get("notified"):
                    entries.append(WaitlistEntry(
                        session_id=data["session_id"],
                        product_id=data["product_id"],
                        product_name=data.get("product_name", ""),
                        phone=data.get("phone"),
                        created_at=data.get("created_at", ""),
                        notified=data.get("notified", False),
                        notified_at=data.get("notified_at"),
                    ))
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    def mark_notified(self, product_id: str) -> list[str]:
        """Mark all waitlist entries for product as notified. Returns list of phones notified."""
        if not _WAITLIST_PATH.exists():
            return []
        lines = _WAITLIST_PATH.read_text(encoding="utf-8").splitlines()
        now = datetime.now(timezone.utc).isoformat()
        phones: list[str] = []
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                new_lines.append(line)
                continue
            try:
                data = json.loads(stripped)
                if data.get("product_id") == product_id and not data.get("notified"):
                    data["notified"] = True
                    data["notified_at"] = now
                    if data.get("phone"):
                        phones.append(data["phone"])
                new_lines.append(json.dumps(data, ensure_ascii=False))
            except json.JSONDecodeError:
                new_lines.append(stripped)
        _WAITLIST_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return phones

    def get_all_pending(self) -> list[WaitlistEntry]:
        entries: list[WaitlistEntry] = []
        if not _WAITLIST_PATH.exists():
            return entries
        for line in _WAITLIST_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if not data.get("notified"):
                    entries.append(WaitlistEntry(
                        session_id=data["session_id"],
                        product_id=data["product_id"],
                        product_name=data.get("product_name", ""),
                        phone=data.get("phone"),
                        created_at=data.get("created_at", ""),
                    ))
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    def is_waitlist_request(self, text: str) -> bool:
        normalized = text.casefold()
        return any(phrase in normalized for phrase in WAITLIST_PHRASES)

    def get_status(self) -> dict[str, Any]:
        if not _WAITLIST_PATH.exists():
            return {"total_entries": 0, "pending_notifications": 0, "products_with_waitlist": 0}
        entries = []
        for line in _WAITLIST_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                try:
                    entries.append(json.loads(stripped))
                except json.JSONDecodeError:
                    pass
        pending = [e for e in entries if not e.get("notified")]
        products = len({e["product_id"] for e in pending})
        return {
            "total_entries": len(entries),
            "pending_notifications": len(pending),
            "products_with_waitlist": products,
        }


def check_restock_and_notify(
    product_id: str,
    new_stock: int,
    old_stock: int,
    product_name: str,
) -> list[str]:
    """Called by POS sync when stock changes from 0 → positive. Returns phones to notify."""
    if old_stock > 0 or new_stock <= 0:
        return []
    manager = WaitlistManager()
    phones = manager.mark_notified(product_id)
    if phones:
        # In production: send SMS/WhatsApp via gateway API
        # For now: log that notification would be sent
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            "Restock notification triggered",
            extra={"product_id": product_id, "product_name": product_name, "phones": phones},
        )
    return phones
