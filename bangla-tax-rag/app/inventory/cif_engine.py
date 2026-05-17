"""CIF-RAG orchestration layer.

This engine wraps the existing image-search decision with the new CIF-RAG
architecture artifacts: factor graph, counterfactual plan, claim contracts,
and risk-cost judgment. It deliberately preserves the current answer unless a
caller chooses to act on `risk_decision.final_label`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.schemas import InventoryItemRecord
from app.inventory.commerce_claims import ClaimContractResult, CommerceClaimCompiler
from app.inventory.counterfactual_planner import CounterfactualPlan, CounterfactualQueryPlanner
from app.inventory.image_matcher import ImageSearchDecision
from app.inventory.product_factor_graph import ProductFactorGraph
from app.inventory.product_factors import factorize_product
from app.inventory.risk_decision_automaton import RiskCostDecisionAutomaton, RiskDecision


@dataclass(frozen=True)
class CifRagResult:
    plan: CounterfactualPlan
    claims: ClaimContractResult
    risk_decision: RiskDecision
    primary_product_graph: dict[str, Any]
    primary_factors: dict[str, Any] | None

    def to_trace(self) -> dict[str, Any]:
        return {
            "architecture": "CIF-RAG",
            "plan": self.plan.to_dict(),
            "claims": self.claims.to_dict(),
            "risk_decision": self.risk_decision.to_dict(),
            "primary_product_graph": self.primary_product_graph,
            "primary_factors": self.primary_factors,
        }


class CifRagEngine:
    """Build a CIF-RAG trace for an image-search decision."""

    def __init__(self, catalog: dict[str, InventoryItemRecord]) -> None:
        self.catalog = catalog
        self.graph = ProductFactorGraph.from_catalog(catalog)
        self.planner = CounterfactualQueryPlanner()
        self.risk_automaton = RiskCostDecisionAutomaton()

    def analyze(
        self,
        *,
        query_text: str,
        has_image: bool,
        decision: ImageSearchDecision,
        memory_anchor_product_id: str | None = None,
    ) -> CifRagResult:
        plan = self.planner.plan(
            query_text=query_text,
            has_image=has_image,
            memory_anchor_product_id=memory_anchor_product_id,
        )
        claims = CommerceClaimCompiler(self.graph).compile(plan=plan, decision=decision)
        risk = self.risk_automaton.evaluate(
            plan=plan,
            decision=decision,
            claim_contract=claims,
            graph=self.graph,
        )
        primary = self.catalog.get(decision.primary_product_id or "")
        primary_factors = factorize_product(primary).to_dict() if primary else None
        return CifRagResult(
            plan=plan,
            claims=claims,
            risk_decision=risk,
            primary_product_graph=self.graph.trace_for_product(decision.primary_product_id),
            primary_factors=primary_factors,
        )
