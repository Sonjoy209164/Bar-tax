from __future__ import annotations

from app.core.schemas import InventorySearchHit
from app.inventory.ontology import ProductOntology
from app.inventory.preferences import InventoryPreferenceProfile


class InventoryTradeoffReasoner:
    """Turns product-plan relationships into honest customer-facing tradeoffs."""

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()

    def build_tradeoffs(
        self,
        *,
        primary: InventorySearchHit | None,
        alternatives: list[InventorySearchHit],
        cross_sells: list[InventorySearchHit],
        preferences: InventoryPreferenceProfile,
    ) -> list[str]:
        if primary is None:
            return []

        tradeoffs: list[str] = []
        if alternatives:
            alternative = alternatives[0]
            tradeoffs.extend(
                [
                    self._price_tradeoff(primary=primary, alternative=alternative, preferences=preferences),
                    self._product_type_tradeoff(primary=primary, alternative=alternative, preferences=preferences),
                    self._premium_budget_tradeoff(primary=primary, alternative=alternative, preferences=preferences),
                    self._stock_tradeoff(primary=primary, alternative=alternative),
                ]
            )

        tradeoffs.extend(
            [
                self._primary_stock_warning(primary),
                self._cross_sell_boundary(primary=primary, cross_sells=cross_sells),
            ]
        )
        return self._clean(tradeoffs)[:7]

    def _price_tradeoff(
        self,
        *,
        primary: InventorySearchHit,
        alternative: InventorySearchHit,
        preferences: InventoryPreferenceProfile,
    ) -> str | None:
        if primary.price is None or alternative.price is None:
            return None
        if alternative.price < primary.price:
            price_gap = primary.price - alternative.price
            if preferences.quality_level == "premium":
                return (
                    f"{alternative.name} is cheaper by {self._format_money(price_gap, primary.currency)}, "
                    f"but {primary.name} remains the stronger premium lead."
                )
            return (
                f"{alternative.name} is the lower-price fallback at {self._format_price(alternative)}, "
                f"while {primary.name} costs {self._format_price(primary)}."
            )
        if alternative.price > primary.price:
            return (
                f"{alternative.name} is a step-up at {self._format_price(alternative)}, "
                f"so position it only if the customer accepts a higher budget than {self._format_price(primary)}."
            )
        return f"{alternative.name} and {primary.name} have the same listed price at {self._format_price(primary)}."

    def _product_type_tradeoff(
        self,
        *,
        primary: InventorySearchHit,
        alternative: InventorySearchHit,
        preferences: InventoryPreferenceProfile,
    ) -> str | None:
        primary_type = self.ontology.detect_product_type(product=primary)
        alternative_type = self.ontology.detect_product_type(product=alternative)
        if not primary_type or not alternative_type or primary_type == alternative_type:
            return None

        if primary_type == "headphones" and alternative_type == "earbuds":
            return (
                f"{alternative.name} is a cheaper audio fallback, but it is earbuds, "
                f"not an equivalent over-ear headphone substitute for {primary.name}."
            )

        requested_type = preferences.product_type or primary_type
        return (
            f"{alternative.name} is related as {alternative_type}, but it is not an exact "
            f"{requested_type} substitute."
        )

    def _premium_budget_tradeoff(
        self,
        *,
        primary: InventorySearchHit,
        alternative: InventorySearchHit,
        preferences: InventoryPreferenceProfile,
    ) -> str | None:
        if preferences.quality_level == "premium" and alternative.price is not None and primary.price is not None:
            if alternative.price < primary.price:
                return (
                    f"Use {primary.name} for the premium pitch and keep {alternative.name} as the budget-control option."
                )
        if preferences.quality_level == "budget" and alternative.price is not None and primary.price is not None:
            if alternative.price > primary.price:
                return (
                    f"Use {primary.name} for budget fit and {alternative.name} only as a feature or quality step-up."
                )
        return None

    def _stock_tradeoff(
        self,
        *,
        primary: InventorySearchHit,
        alternative: InventorySearchHit,
    ) -> str | None:
        primary_stock = primary.stock if primary.stock is not None else None
        alternative_stock = alternative.stock if alternative.stock is not None else None
        if primary_stock is not None and primary_stock <= 0 and alternative_stock and alternative_stock > 0:
            return (
                f"{alternative.name} is the practical in-stock alternative because {primary.name} is currently out of stock."
            )
        if primary_stock is not None and 0 < primary_stock <= 5 and alternative_stock and alternative_stock > primary_stock:
            return (
                f"{primary.name} is the better-fit lead, but {alternative.name} has safer availability with {alternative_stock} in stock."
            )
        return None

    def _primary_stock_warning(self, primary: InventorySearchHit) -> str | None:
        if primary.stock is None:
            return None
        if primary.stock <= 0:
            return f"{primary.name} should not be pitched as immediately sellable because current stock is 0."
        if primary.stock <= 5:
            return f"{primary.name} has limited stock, so mention urgency without overpromising availability."
        return None

    def _cross_sell_boundary(
        self,
        *,
        primary: InventorySearchHit,
        cross_sells: list[InventorySearchHit],
    ) -> str | None:
        if not cross_sells:
            return None
        cross_sell = cross_sells[0]
        return (
            f"{cross_sell.name} is a cross-sell add-on for {primary.name}, not a substitute; "
            "present it only when the customer wants a bundle or fuller setup."
        )

    @staticmethod
    def _format_price(hit: InventorySearchHit) -> str:
        if hit.price is None:
            return "price not listed"
        return f"{hit.currency or 'USD'} {hit.price:.2f}"

    @staticmethod
    def _format_money(amount: float, currency: str | None) -> str:
        return f"{currency or 'USD'} {amount:.2f}"

    @staticmethod
    def _clean(tradeoffs: list[str | None]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for tradeoff in tradeoffs:
            if not tradeoff or tradeoff in seen:
                continue
            seen.add(tradeoff)
            cleaned.append(tradeoff)
        return cleaned
