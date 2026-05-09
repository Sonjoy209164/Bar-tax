from __future__ import annotations

from typing import Any

from app.core.schemas import InventoryItemRecord


_LOW_STOCK_THRESHOLD = 3

_CROSS_SELL_CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "saree":    ("bag", "jewelry", "shoes", "blouse"),
    "panjabi":  ("shoes", "bag", "watch"),
    "kurti":    ("bag", "shoes", "jewelry"),
    "blouse":   ("saree",),
    "salwar":   ("bag", "shoes", "dupatta"),
    "lehenga":  ("jewelry", "bag", "shoes"),
    "shoes":    ("bag",),
    "bag":      ("jewelry",),
}


def low_stock_notice(items: list[InventoryItemRecord], product_ids: list[str]) -> str | None:
    """Return a notice string if any shown product has low stock."""
    low = [
        item for pid in product_ids[:4]
        if (item := next((i for i in items if i.product_id == pid), None)) is not None
        and 0 < item.stock <= _LOW_STOCK_THRESHOLD
    ]
    if not low:
        return None
    names = ", ".join(f"**{i.name}** ({i.stock} left)" for i in low[:2])
    return f"⚠ Low stock: {names} — order soon to avoid missing out."


def proactive_cross_sell(
    primary_category: str | None,
    catalog: dict[str, InventoryItemRecord],
    color_hint: str | None = None,
    budget_max: float | None = None,
    top_k: int = 3,
) -> list[InventoryItemRecord]:
    """Return in-stock accessories that complement the primary category."""
    if not primary_category:
        return []
    target_keys = _CROSS_SELL_CATEGORY_MAP.get(primary_category, ())
    if not target_keys:
        return []

    candidates: list[tuple[float, InventoryItemRecord]] = []
    for item in catalog.values():
        if item.stock <= 0:
            continue
        item_cat = (item.attributes.get("category_key") or "").casefold()
        if item_cat not in target_keys:
            continue
        if budget_max and item.price and item.price > budget_max:
            continue

        score = 1.0
        if color_hint and (item.attributes.get("color") or "").casefold() == color_hint.casefold():
            score += 0.5
        elif color_hint and color_hint.casefold() in (item.tags or []):
            score += 0.2
        candidates.append((score, item))

    candidates.sort(key=lambda t: -t[0])
    return [item for _, item in candidates[:top_k]]


def build_proactive_message(
    answer: str,
    catalog: dict[str, InventoryItemRecord],
    recommended_ids: list[str],
    primary_category: str | None,
    color_hint: str | None = None,
    budget_max: float | None = None,
) -> str:
    """Append low-stock notice and cross-sell suggestions to an existing answer."""
    items_list = list(catalog.values())
    parts: list[str] = [answer]

    notice = low_stock_notice(items_list, recommended_ids)
    if notice:
        parts.append("\n" + notice)

    cross_sell = proactive_cross_sell(primary_category, catalog, color_hint, budget_max)
    if cross_sell:
        lines = ["\n💡 You might also like:"]
        for item in cross_sell:
            price_str = f"BDT {item.price:,.0f}" if item.price else ""
            lines.append(f"  • {item.name}" + (f" — {price_str}" if price_str else ""))
        parts.append("\n".join(lines))

    return "".join(parts)


def restock_suggestion(
    catalog: dict[str, InventoryItemRecord],
    product_id: str,
) -> str | None:
    """If item is out of stock, suggest similar in-stock alternatives."""
    item = catalog.get(product_id)
    if item is None or item.stock > 0:
        return None
    cat = item.attributes.get("category_key")
    color = item.attributes.get("color")
    fabric = item.attributes.get("fabric")
    alternatives = [
        i for i in catalog.values()
        if i.product_id != product_id
        and i.stock > 0
        and i.attributes.get("category_key") == cat
        and (i.attributes.get("color") == color or i.attributes.get("fabric") == fabric)
    ]
    if not alternatives:
        return None
    alt = alternatives[0]
    return f"That item is out of stock. Similar in-stock option: **{alt.name}** — {f'BDT {alt.price:,.0f}' if alt.price else ''}, {alt.stock} available."
