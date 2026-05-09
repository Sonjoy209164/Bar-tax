"""Tests for proactive recommendations module."""
import pytest

from app.core.schemas import InventoryItemRecord
from app.inventory.proactive import (
    build_proactive_message,
    low_stock_notice,
    proactive_cross_sell,
    restock_suggestion,
)


def _make_item(pid: str, name: str, category: str, stock: int, price: float = 1000.0, color: str = "red") -> InventoryItemRecord:
    return InventoryItemRecord(
        product_id=pid,
        sku=pid,
        name=name,
        category=category,
        stock=stock,
        price=price,
        attributes={"category_key": category, "color": color},
    )


@pytest.fixture()
def catalog() -> dict[str, InventoryItemRecord]:
    return {
        "s1": _make_item("s1", "Red Saree", "saree", 2, 5000.0),
        "b1": _make_item("b1", "Gold Bag", "bag", 10, 800.0, "gold"),
        "j1": _make_item("j1", "Pearl Jewelry", "jewelry", 0, 1200.0),
    }


def test_low_stock_notice_triggered(catalog: dict[str, InventoryItemRecord]) -> None:
    items = list(catalog.values())
    notice = low_stock_notice(items, ["s1"])
    assert notice is not None
    assert "s1" in notice or "Red Saree" in notice


def test_low_stock_notice_not_triggered_for_high_stock(catalog: dict[str, InventoryItemRecord]) -> None:
    items = list(catalog.values())
    notice = low_stock_notice(items, ["b1"])
    assert notice is None


def test_proactive_cross_sell_finds_accessories(catalog: dict[str, InventoryItemRecord]) -> None:
    results = proactive_cross_sell("saree", catalog)
    assert any(r.attributes.get("category_key") in ("bag", "jewelry", "shoes") for r in results)


def test_proactive_cross_sell_excludes_out_of_stock(catalog: dict[str, InventoryItemRecord]) -> None:
    results = proactive_cross_sell("saree", catalog)
    assert all(r.stock > 0 for r in results)


def test_proactive_cross_sell_empty_for_unknown_category(catalog: dict[str, InventoryItemRecord]) -> None:
    results = proactive_cross_sell("unknown_category", catalog)
    assert results == []


def test_build_proactive_message_appends_cross_sell(catalog: dict[str, InventoryItemRecord]) -> None:
    msg = build_proactive_message("Here are sarees.", catalog, ["s1"], "saree")
    assert "Here are sarees." in msg


def test_build_proactive_message_no_crash_empty_catalog() -> None:
    msg = build_proactive_message("No results.", {}, [], None)
    assert msg == "No results."


def test_restock_suggestion_returns_alternative(catalog: dict[str, InventoryItemRecord]) -> None:
    # j1 is out of stock (jewelry), but s1 is in stock (saree) — different category
    # We need same-category comparison. Add an in-stock jewelry item.
    catalog["j2"] = _make_item("j2", "Silver Jewelry", "jewelry", 5, 900.0)
    suggestion = restock_suggestion(catalog, "j1")
    assert suggestion is not None
    assert "Silver Jewelry" in suggestion


def test_restock_suggestion_none_when_in_stock(catalog: dict[str, InventoryItemRecord]) -> None:
    assert restock_suggestion(catalog, "s1") is None
