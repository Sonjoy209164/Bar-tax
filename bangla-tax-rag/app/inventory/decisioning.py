from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.schemas import InventoryBusinessSignalRecord, InventoryItemRecord, InventorySearchHit
from app.inventory.ontology import ProductOntology


@dataclass(frozen=True)
class InventoryDecisionScore:
    strategy: str
    score: float = 0.0
    components: dict[str, float | str] = field(default_factory=dict)
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_debug_dict(self) -> dict[str, Any]:
        prefix = f"deterministic_{self.strategy}"
        return {
            f"{prefix}_score": round(self.score, 4),
            f"{prefix}_components": {
                key: round(value, 4) if isinstance(value, (int, float)) else value
                for key, value in self.components.items()
            },
            f"{prefix}_reasons": list(self.reasons),
        }


class InventoryDecisionScorer:
    """Produces deterministic, explanation-friendly ranking scores for inventory decisions."""

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()

    def rank_recommendations(
        self,
        *,
        hits: list[InventorySearchHit],
        sales_style: str,
    ) -> list[InventorySearchHit]:
        if not hits:
            return []
        prices = [hit.price for hit in hits if hit.price is not None]
        price_min = min(prices) if prices else None
        price_max = max(prices) if prices else None
        max_stock = max((max(hit.stock or 0, 0) for hit in hits), default=0)
        scored_hits: list[tuple[InventorySearchHit, float]] = []
        for hit in hits:
            decision = self._recommendation_score(
                hit=hit,
                sales_style=sales_style,
                price_min=price_min,
                price_max=price_max,
                max_stock=max_stock,
            )
            scored_hits.append((self._merge_decision(hit=hit, decision=decision), decision.score))
        return [
            hit
            for hit, _ in sorted(
                scored_hits,
                key=lambda item: (
                    -item[1],
                    self._is_out_of_stock(item[0]),
                    -self._score_value(item[0], "final_score", fallback=item[0].score),
                    self._price_sort_key(item[0]),
                    item[0].name.casefold(),
                ),
            )
        ]

    def rank_sales_alternatives(
        self,
        *,
        primary: InventorySearchHit,
        hits: list[InventorySearchHit],
        sales_style: str,
    ) -> list[InventorySearchHit]:
        if not hits:
            return []
        eligible_hits = [
            hit
            for hit in hits
            if hit.product_id != primary.product_id and self.ontology.valid_alternative(primary, hit)
        ]
        if not eligible_hits:
            return []
        scored_hits: list[tuple[InventorySearchHit, float]] = []
        for hit in eligible_hits:
            decision = self._alternative_score(
                primary=primary,
                candidate=hit,
                sales_style=sales_style,
            )
            scored_hits.append((self._merge_decision(hit=hit, decision=decision), decision.score))
        return [
            hit
            for hit, _ in sorted(
                scored_hits,
                key=lambda item: (
                    -item[1],
                    self._is_out_of_stock(item[0]),
                    -self._score_value(
                        item[0],
                        "deterministic_recommendation_score",
                        fallback=self._score_value(item[0], "final_score", fallback=item[0].score),
                    ),
                    self._alternative_distance_sort_key(primary=primary, candidate=item[0], sales_style=sales_style),
                    item[0].name.casefold(),
                ),
            )
        ]

    def select_sales_alternative(
        self,
        *,
        primary: InventorySearchHit,
        hits: list[InventorySearchHit],
        sales_style: str,
    ) -> InventorySearchHit | None:
        ranked = self.rank_sales_alternatives(
            primary=primary,
            hits=hits,
            sales_style=sales_style,
        )
        return ranked[0] if ranked else None

    def select_comparison_pair(
        self,
        *,
        hits: list[InventorySearchHit],
    ) -> tuple[list[InventorySearchHit], InventorySearchHit | None, InventorySearchHit | None]:
        if not hits:
            return [], None, None
        scored_hits = [self._merge_decision(hit=hit, decision=self._comparison_score(hit=hit)) for hit in hits]
        ranked_hits = sorted(
            scored_hits,
            key=lambda hit: (
                -self._score_value(hit, "deterministic_comparison_score", fallback=hit.score),
                self._is_out_of_stock(hit),
                hit.name.casefold(),
            ),
        )
        primary = ranked_hits[0]
        alternative = next(
            (hit for hit in ranked_hits[1:] if self.ontology.valid_alternative(primary, hit)),
            ranked_hits[1] if len(ranked_hits) > 1 else None,
        )
        return ranked_hits, primary, alternative

    def rank_restock_candidates(
        self,
        *,
        candidates: list[tuple[InventorySearchHit, InventoryItemRecord, InventoryBusinessSignalRecord]],
    ) -> list[InventorySearchHit]:
        if not candidates:
            return []
        max_units_sold = max((signal.units_sold or 0 for _, _, signal in candidates), default=0)
        max_orders = max((signal.order_count or 0 for _, _, signal in candidates), default=0)
        max_lead_time = max((signal.supplier_lead_time_days or 0 for _, _, signal in candidates), default=0)
        scored_hits: list[tuple[InventorySearchHit, float]] = []
        for hit, item, signal in candidates:
            decision = self._restock_score(
                hit=hit,
                item=item,
                signal=signal,
                max_units_sold=max_units_sold,
                max_orders=max_orders,
                max_lead_time=max_lead_time,
            )
            scored_hits.append((self._merge_decision(hit=hit, decision=decision), decision.score))
        return [
            hit
            for hit, _ in sorted(
                scored_hits,
                key=lambda item: (
                    -item[1],
                    self._is_out_of_stock(item[0]),
                    self._price_sort_key(item[0]),
                    item[0].name.casefold(),
                ),
            )
        ]

    def _recommendation_score(
        self,
        *,
        hit: InventorySearchHit,
        sales_style: str,
        price_min: float | None,
        price_max: float | None,
        max_stock: int,
    ) -> InventoryDecisionScore:
        reranker_fit = self._score_value(hit, "final_score", fallback=hit.score)
        type_fit = max(
            self._score_value(hit, "product_type_match"),
            self._score_value(hit, "family_match") * 0.85,
            self._score_value(hit, "category_match") * 0.65,
        )
        evidence_support = max(
            self._score_value(hit, "structured_spec_match"),
            self._score_value(hit, "metadata_match"),
            min(len(hit.attributes), 4) / 4 if hit.attributes else 0.0,
        )
        availability = self._availability_support(hit=hit, max_stock=max_stock)
        style_fit = self._recommendation_style_fit(
            hit=hit,
            sales_style=sales_style,
            price_min=price_min,
            price_max=price_max,
        )
        components = {
            "reranker_fit": reranker_fit,
            "type_fit": type_fit,
            "evidence_support": evidence_support,
            "availability": availability,
            "style_fit": style_fit,
        }
        total = (
            reranker_fit * 0.52
            + type_fit * 0.18
            + evidence_support * 0.10
            + availability * 0.12
            + style_fit * 0.08
        )
        if self._is_out_of_stock(hit):
            total *= 0.65
        reasons = self._recommendation_reasons(
            hit=hit,
            sales_style=sales_style,
            components=components,
            price_min=price_min,
            price_max=price_max,
        )
        return InventoryDecisionScore(
            strategy="recommendation",
            score=self._clamp(total),
            components=components,
            reasons=tuple(reasons),
        )

    def _comparison_score(self, *, hit: InventorySearchHit) -> InventoryDecisionScore:
        reranker_fit = self._score_value(hit, "final_score", fallback=hit.score)
        comparability = max(
            self._score_value(hit, "product_type_match"),
            self._score_value(hit, "family_match") * 0.9,
            self._score_value(hit, "category_match") * 0.7,
        )
        completeness = sum(
            [
                1.0 if hit.price is not None else 0.0,
                1.0 if hit.stock is not None else 0.0,
                1.0 if hit.attributes or self._score_value(hit, "structured_spec_match") > 0 else 0.0,
            ]
        ) / 3.0
        evidence_support = max(self._score_value(hit, "structured_spec_match"), self._score_value(hit, "metadata_match"))
        components = {
            "reranker_fit": reranker_fit,
            "comparability": comparability,
            "completeness": completeness,
            "evidence_support": evidence_support,
        }
        reasons: list[str] = []
        if comparability >= 0.85:
            reasons.append("it is an exact comparison-fit product for the requested type")
        elif comparability >= 0.45:
            reasons.append("it stays inside the same product family for a fair side-by-side")
        if completeness >= 0.9:
            reasons.append("price, stock, and core facts are all available for comparison")
        elif completeness >= 0.6:
            reasons.append("enough core facts are present for a grounded comparison")
        if evidence_support >= 0.6:
            reasons.append("structured evidence supports the comparison")
        return InventoryDecisionScore(
            strategy="comparison",
            score=self._clamp(
                reranker_fit * 0.45
                + comparability * 0.30
                + completeness * 0.17
                + evidence_support * 0.08
            ),
            components=components,
            reasons=tuple(reasons[:4]),
        )

    def _restock_score(
        self,
        *,
        hit: InventorySearchHit,
        item: InventoryItemRecord,
        signal: InventoryBusinessSignalRecord,
        max_units_sold: int,
        max_orders: int,
        max_lead_time: int,
    ) -> InventoryDecisionScore:
        inventory_level = signal.inventory_on_hand if signal.inventory_on_hand is not None else item.stock
        stock_pressure = self._stock_pressure(inventory_level)
        demand_signal = max(
            self._clamp(signal.demand_score or 0.0),
            self._normalize(signal.units_sold or 0, max_units_sold),
            self._normalize(signal.order_count or 0, max_orders),
        )
        lead_time = self._normalize(signal.supplier_lead_time_days or 0, max_lead_time)
        margin = self._clamp(signal.gross_margin_rate or 0.0)
        supplier_risk = self._clamp(signal.supplier_risk_score or 0.0)
        return_penalty = self._clamp(signal.return_rate or 0.0)
        components = {
            "stock_pressure": stock_pressure,
            "demand_signal": demand_signal,
            "lead_time": lead_time,
            "margin": margin,
            "supplier_risk": supplier_risk,
            "return_penalty": return_penalty,
        }
        total = (
            stock_pressure * 0.33
            + demand_signal * 0.27
            + lead_time * 0.16
            + margin * 0.14
            + supplier_risk * 0.08
            - return_penalty * 0.08
        )
        reasons: list[str] = []
        if stock_pressure >= 0.9:
            reasons.append("stock pressure is critical")
        elif stock_pressure >= 0.65:
            reasons.append("inventory is tight enough to create real restock urgency")
        if demand_signal >= 0.8:
            reasons.append("demand is among the strongest in the current set")
        elif demand_signal >= 0.5:
            reasons.append("demand is solid relative to the current set")
        if lead_time >= 0.6:
            reasons.append("supplier lead time is long enough that waiting increases risk")
        if margin >= 0.25:
            reasons.append("margin impact supports prioritizing this replenishment")
        return InventoryDecisionScore(
            strategy="restock",
            score=self._clamp(total),
            components=components,
            reasons=tuple(reasons[:4]),
        )

    def _alternative_score(
        self,
        *,
        primary: object,
        candidate: object,
        sales_style: str,
    ) -> InventoryDecisionScore:
        relationship_fit = self._alternative_relationship_fit(primary=primary, candidate=candidate)
        availability = self._entity_availability_support(candidate)
        recommendation_fit = max(
            self._entity_score_value(candidate, "deterministic_recommendation_score"),
            self._entity_score_value(candidate, "final_score", fallback=self._entity_score(candidate)),
        )
        role_fit = self._alternative_role_fit(
            primary=primary,
            candidate=candidate,
            sales_style=sales_style,
        )
        quality_support = self._entity_quality_support(candidate)
        components = {
            "relationship_fit": relationship_fit,
            "availability": availability,
            "recommendation_fit": recommendation_fit,
            "role_fit": role_fit,
            "quality_support": quality_support,
        }
        if sales_style == "budget":
            total = (
                relationship_fit * 0.30
                + availability * 0.18
                + recommendation_fit * 0.16
                + role_fit * 0.26
                + quality_support * 0.10
            )
        elif sales_style == "premium":
            total = (
                relationship_fit * 0.34
                + availability * 0.22
                + recommendation_fit * 0.18
                + role_fit * 0.18
                + quality_support * 0.08
            )
        else:
            total = (
                relationship_fit * 0.32
                + availability * 0.24
                + recommendation_fit * 0.20
                + role_fit * 0.14
                + quality_support * 0.10
            )
        if self._entity_out_of_stock(candidate):
            total *= 0.6
        reasons = self._alternative_reasons(
            primary=primary,
            candidate=candidate,
            sales_style=sales_style,
            components=components,
        )
        return InventoryDecisionScore(
            strategy="alternative",
            score=self._clamp(total),
            components={**components, "role": self._alternative_role(primary=primary, candidate=candidate, sales_style=sales_style)},
            reasons=tuple(reasons[:4]),
        )

    def _recommendation_style_fit(
        self,
        *,
        hit: InventorySearchHit,
        sales_style: str,
        price_min: float | None,
        price_max: float | None,
    ) -> float:
        budget_fit = self._score_value(hit, "budget_fit")
        premium_fit = self._score_value(hit, "premium_fit")
        price_fit = self._score_value(hit, "price_fit")
        normalized_price = self._normalized_price_position(hit=hit, price_min=price_min, price_max=price_max)
        if sales_style == "budget":
            return max(budget_fit, price_fit, 1.0 - normalized_price)
        if sales_style == "premium":
            return max(premium_fit, normalized_price)
        if sales_style == "availability":
            return self._availability_support(hit=hit, max_stock=max(hit.stock or 0, 1))
        if sales_style == "urgency":
            stock = hit.stock if hit.stock is not None else 0
            if stock <= 0:
                return 0.0
            if stock <= 2:
                return 1.0
            if stock <= 5:
                return 0.8
            if stock <= 10:
                return 0.55
            return 0.3
        return max(price_fit, budget_fit, premium_fit)

    def _recommendation_reasons(
        self,
        *,
        hit: InventorySearchHit,
        sales_style: str,
        components: dict[str, float],
        price_min: float | None,
        price_max: float | None,
    ) -> list[str]:
        reasons: list[str] = []
        if components["type_fit"] >= 0.85:
            reasons.append("it is the strongest exact-fit match")
        elif components["type_fit"] >= 0.45:
            reasons.append("it stays in the closest product family")
        if components["availability"] >= 0.8:
            reasons.append("availability is strong enough to support a confident recommendation")
        elif not self._is_out_of_stock(hit) and hit.stock is not None:
            reasons.append(f"current stock of {hit.stock} keeps it sellable")
        if sales_style == "budget" and hit.price is not None:
            normalized_price = self._normalized_price_position(hit=hit, price_min=price_min, price_max=price_max)
            if normalized_price <= 0.2:
                reasons.append("it sits at the value end of the current shortlist")
            elif self._score_value(hit, "price_fit") >= 0.8:
                reasons.append("it still fits the requested budget well")
        elif sales_style == "premium" and hit.price is not None:
            normalized_price = self._normalized_price_position(hit=hit, price_min=price_min, price_max=price_max)
            if normalized_price >= 0.8:
                reasons.append("it carries the strongest premium price position in the shortlist")
            elif self._score_value(hit, "premium_fit") >= 0.8:
                reasons.append("its premium signals back up a stronger pitch")
        elif components["evidence_support"] >= 0.6:
            reasons.append("structured evidence support is stronger than the nearby options")
        return reasons[:4]

    def _alternative_reasons(
        self,
        *,
        primary: object,
        candidate: object,
        sales_style: str,
        components: dict[str, float],
    ) -> list[str]:
        reasons: list[str] = []
        role = self._alternative_role(primary=primary, candidate=candidate, sales_style=sales_style)
        if components["relationship_fit"] >= 0.95:
            reasons.append("it stays in the exact same product type")
        elif components["relationship_fit"] >= 0.75:
            reasons.append("it stays in the closest product family")
        if role == "fallback":
            reasons.append(f"it gives you a more accessible fallback than {self._entity_name(primary)}")
        elif role == "step_up":
            reasons.append(f"it creates a cleaner step-up from {self._entity_name(primary)}")
        if components["recommendation_fit"] >= 0.72:
            reasons.append("its overall recommendation support is still strong")
        if components["availability"] >= 0.8:
            reasons.append("stock is healthy enough to keep it sellable")
        elif not self._entity_out_of_stock(candidate) and self._entity_stock(candidate) is not None:
            reasons.append(f"current stock of {self._entity_stock(candidate)} keeps it usable")
        if components["quality_support"] >= 0.65:
            reasons.append("the catalog evidence is complete enough to pitch confidently")
        return reasons[:4]

    @staticmethod
    def _merge_decision(hit: InventorySearchHit, decision: InventoryDecisionScore) -> InventorySearchHit:
        merged_evidence = {
            **hit.evidence_scores,
            **decision.to_debug_dict(),
        }
        decision_score = decision.score
        return hit.model_copy(update={"score": round(max(hit.score, decision_score), 4), "evidence_scores": merged_evidence})

    @staticmethod
    def _score_value(hit: InventorySearchHit, key: str, fallback: float = 0.0) -> float:
        value = hit.evidence_scores.get(key)
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        return max(0.0, min(1.0, float(fallback)))

    @staticmethod
    def _entity_scores(entity: object) -> dict[str, Any]:
        if isinstance(getattr(entity, "evidence_scores", None), dict):
            return getattr(entity, "evidence_scores")
        if isinstance(getattr(entity, "score_breakdown", None), dict):
            return getattr(entity, "score_breakdown")
        return {}

    def _entity_score_value(self, entity: object, key: str, fallback: float = 0.0) -> float:
        value = self._entity_scores(entity).get(key)
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        return max(0.0, min(1.0, float(fallback)))

    @staticmethod
    def _entity_score(entity: object) -> float:
        value = getattr(entity, "score", 0.0)
        if isinstance(value, (int, float)):
            return float(value)
        return 0.0

    @staticmethod
    def _entity_name(entity: object) -> str:
        value = getattr(entity, "name", None)
        return value if isinstance(value, str) and value else "this option"

    @staticmethod
    def _entity_price(entity: object) -> float | None:
        value = getattr(entity, "price", None)
        return float(value) if isinstance(value, (int, float)) else None

    @staticmethod
    def _entity_stock(entity: object) -> int | None:
        value = getattr(entity, "stock", None)
        return int(value) if isinstance(value, int) else None

    @staticmethod
    def _entity_snippet(entity: object) -> str:
        value = getattr(entity, "snippet", None)
        return value if isinstance(value, str) else ""

    @staticmethod
    def _entity_tags(entity: object) -> list[str]:
        tags = getattr(entity, "tags", None)
        if isinstance(tags, list):
            return [tag for tag in tags if isinstance(tag, str)]
        return []

    def _entity_availability_support(self, entity: object) -> float:
        stock = self._entity_stock(entity)
        if stock is None:
            return 0.15
        if stock <= 0:
            return 0.0
        if stock <= 2:
            return 0.55
        if stock <= 5:
            return 0.75
        if stock <= 10:
            return 0.9
        return 1.0

    def _entity_out_of_stock(self, entity: object) -> bool:
        stock = self._entity_stock(entity)
        return stock is None or stock <= 0

    def _entity_quality_support(self, entity: object) -> float:
        score = 0
        name = self._entity_name(entity)
        if len(name.strip()) >= 4:
            score += 2
        category = getattr(entity, "category", None)
        if isinstance(category, str) and len(category.strip()) >= 3:
            score += 1
        brand = getattr(entity, "brand", None)
        if isinstance(brand, str) and len(brand.strip()) >= 3:
            score += 1
        if len(self._entity_snippet(entity).strip()) >= 18:
            score += 2
        if self._entity_price(entity) is not None:
            score += 1
        if self._entity_stock(entity) is not None:
            score += 1
        if self._entity_tags(entity):
            score += 1
        return self._clamp(score / 9.0)

    def _alternative_relationship_fit(self, *, primary: object, candidate: object) -> float:
        primary_type = self.ontology.detect_product_type(product=primary)
        candidate_type = self.ontology.detect_product_type(product=candidate)
        if primary_type and candidate_type:
            if primary_type == candidate_type:
                return 1.0
            if self.ontology.product_family(primary_type) == self.ontology.product_family(candidate_type):
                return 0.82
        if self.ontology.valid_alternative(primary, candidate):
            return 0.68
        return 0.0

    def _alternative_role(
        self,
        *,
        primary: object,
        candidate: object,
        sales_style: str,
    ) -> str:
        primary_price = self._entity_price(primary)
        candidate_price = self._entity_price(candidate)
        if sales_style == "premium":
            if candidate_price is not None and primary_price is not None and candidate_price < primary_price:
                return "fallback"
            if self._entity_score_value(candidate, "budget_fit") >= 0.7:
                return "fallback"
        if sales_style == "budget":
            if candidate_price is not None and primary_price is not None and candidate_price > primary_price:
                return "step_up"
            if self._entity_score_value(candidate, "premium_fit") >= 0.7:
                return "step_up"
        return "alternative"

    def _alternative_role_fit(
        self,
        *,
        primary: object,
        candidate: object,
        sales_style: str,
    ) -> float:
        primary_price = self._entity_price(primary)
        candidate_price = self._entity_price(candidate)
        recommendation_fit = max(
            self._entity_score_value(candidate, "deterministic_recommendation_score"),
            self._entity_score_value(candidate, "final_score", fallback=self._entity_score(candidate)),
        )
        if sales_style == "premium":
            if candidate_price is None or primary_price is None:
                return max(0.45, self._entity_score_value(candidate, "budget_fit", fallback=recommendation_fit))
            if candidate_price < primary_price:
                relative_gap = min((primary_price - candidate_price) / max(primary_price, 1.0), 1.0)
                return min(1.0, 0.72 + (1.0 - relative_gap) * 0.18 + self._entity_score_value(candidate, "budget_fit") * 0.10)
            if candidate_price == primary_price:
                return 0.42
            return 0.12
        if sales_style == "budget":
            premium_support = max(
                self._entity_score_value(candidate, "premium_fit"),
                self._entity_score_value(candidate, "structured_spec_match"),
                self._entity_score_value(candidate, "metadata_match"),
            )
            if candidate_price is None or primary_price is None:
                return max(0.4, premium_support)
            if candidate_price > primary_price:
                relative_gap = min((candidate_price - primary_price) / max(primary_price, 1.0), 1.0)
                return min(1.0, 0.58 + (1.0 - relative_gap) * 0.16 + premium_support * 0.26)
            if candidate_price == primary_price:
                return min(0.55, 0.35 + premium_support * 0.20)
            return 0.1
        if candidate_price is None or primary_price is None:
            return 0.5
        relative_gap = min(abs(candidate_price - primary_price) / max(primary_price, 1.0), 1.0)
        closeness = 1.0 - relative_gap
        if sales_style == "availability":
            return min(1.0, 0.4 + self._entity_availability_support(candidate) * 0.4 + closeness * 0.2)
        if sales_style == "urgency":
            return min(1.0, 0.35 + self._entity_availability_support(candidate) * 0.45 + closeness * 0.2)
        return max(0.35, closeness)

    def _alternative_distance_sort_key(
        self,
        *,
        primary: object,
        candidate: object,
        sales_style: str,
    ) -> tuple[float, float]:
        primary_price = self._entity_price(primary)
        candidate_price = self._entity_price(candidate)
        if primary_price is None or candidate_price is None:
            return (1.0, 0.0)
        price_gap = abs(candidate_price - primary_price)
        direction_bias = 0.0
        if sales_style == "premium" and candidate_price >= primary_price:
            direction_bias = 1.0
        if sales_style == "budget" and candidate_price <= primary_price:
            direction_bias = 1.0
        return (direction_bias, price_gap)

    @staticmethod
    def _availability_support(hit: InventorySearchHit, *, max_stock: int) -> float:
        if hit.stock is None:
            return 0.15
        if hit.stock <= 0:
            return 0.0
        stock_ratio = min(max(hit.stock, 0) / max(max_stock, 1), 1.0)
        return min(1.0, 0.45 + stock_ratio * 0.55)

    @staticmethod
    def _stock_pressure(inventory_level: int | None) -> float:
        if inventory_level is None:
            return 0.35
        if inventory_level <= 0:
            return 1.0
        if inventory_level <= 2:
            return 0.95
        if inventory_level <= 5:
            return 0.82
        if inventory_level <= 10:
            return 0.58
        return 0.24

    @staticmethod
    def _normalize(value: int | float, max_value: int | float) -> float:
        if max_value <= 0:
            return 0.0
        return max(0.0, min(1.0, float(value) / float(max_value)))

    @staticmethod
    def _normalized_price_position(
        *,
        hit: InventorySearchHit,
        price_min: float | None,
        price_max: float | None,
    ) -> float:
        if hit.price is None or price_min is None or price_max is None:
            return 0.5
        if price_max <= price_min:
            return 0.5
        return max(0.0, min(1.0, (hit.price - price_min) / (price_max - price_min)))

    @staticmethod
    def _is_out_of_stock(hit: InventorySearchHit) -> bool:
        return hit.stock is None or hit.stock <= 0

    @staticmethod
    def _price_sort_key(hit: InventorySearchHit) -> float:
        if hit.price is None:
            return float("inf")
        return hit.price

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, round(value, 4)))
