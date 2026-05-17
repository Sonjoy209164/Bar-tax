"""Risk-cost decision automaton for CIF-RAG.

The automaton evaluates whether a generated image-search decision is
commercially safe. It does not need to replace the current answer on day one;
it produces a traceable risk judgment and recommended action.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.inventory.commerce_claims import ClaimContractResult, CommerceClaim
from app.inventory.counterfactual_planner import CounterfactualPlan
from app.inventory.image_matcher import ImageSearchDecision
from app.inventory.product_factor_graph import ProductFactorGraph


RISK_COST = {
    "exact_product": 5,
    "same_design_variant": 5,
    "color_availability": 5,
    "absence": 4,
    "size_stock": 5,
    "price": 5,
    "source_trust": 3,
    "similar_style": 2,
}


@dataclass(frozen=True)
class RiskDecision:
    final_label: str
    risk_level: str
    safe_to_answer: bool
    total_risk_cost: int
    unsupported_high_risk_claims: tuple[str, ...] = field(default_factory=tuple)
    issues: tuple[str, ...] = field(default_factory=tuple)
    recommended_actions: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_label": self.final_label,
            "risk_level": self.risk_level,
            "safe_to_answer": self.safe_to_answer,
            "total_risk_cost": self.total_risk_cost,
            "unsupported_high_risk_claims": list(self.unsupported_high_risk_claims),
            "issues": list(self.issues),
            "recommended_actions": list(self.recommended_actions),
        }


class RiskCostDecisionAutomaton:
    """Evaluate commerce risk from decision labels and claim evidence."""

    def evaluate(
        self,
        *,
        plan: CounterfactualPlan,
        decision: ImageSearchDecision,
        claim_contract: ClaimContractResult,
        graph: ProductFactorGraph,
    ) -> RiskDecision:
        issues: list[str] = []
        actions: list[str] = []
        unsupported_high_risk: list[str] = []
        total_cost = 0

        for claim in claim_contract.unsupported_claims:
            cost = RISK_COST.get(claim.claim_type, 1)
            total_cost += cost
            if cost >= 4:
                unsupported_high_risk.append(claim.claim_type)
                issues.append(
                    f"unsupported high-risk claim: {claim.claim_type} missing {', '.join(claim.missing_evidence)}"
                )

        primary_id = decision.primary_product_id
        primary_node = graph.product(primary_id)

        if decision.decision_label == "confirmed_exact" and not graph.can_claim_exact(primary_id):
            issues.append("confirmed_exact lacks product-photo or owner-confirmed identity evidence")
            unsupported_high_risk.append("exact_product")
            total_cost += RISK_COST["exact_product"]
            actions.append("downgrade exact claim to likely_same_design or similar_style")

        if plan.requested_color and decision.decision_label == "confirmed_same_design_variant":
            variants = graph.find_color_variant(primary_id, plan.requested_color)
            if not any(node.stock > 0 for node in variants):
                issues.append(f"requested color {plan.requested_color} is not an in-stock same-design variant")
                unsupported_high_risk.append("color_availability")
                total_cost += RISK_COST["color_availability"]
                actions.append("answer requested color as unavailable and show available colors")

        if plan.requested_size:
            availability = graph.size_availability(primary_id, plan.requested_size)
            if availability is None or not availability.known:
                issues.append(f"requested size {plan.requested_size} lacks authoritative size_stock evidence")
                unsupported_high_risk.append("size_stock")
                total_cost += RISK_COST["size_stock"]
                actions.append("hedge size availability instead of claiming stock")

        if primary_node and primary_node.stock <= 0 and decision.decision_label in {
            "confirmed_exact",
            "confirmed_same_design_variant",
            "likely_same_design",
        }:
            issues.append("primary product has zero stock")
            total_cost += RISK_COST["color_availability"]
            actions.append("prefer in-stock sibling or say out of stock")

        risk_level = _risk_level(total_cost)
        safe_to_answer = not unsupported_high_risk or risk_level in {"low", "medium"}
        final_label = _recommended_label(decision.decision_label, risk_level, unsupported_high_risk)
        if not actions and final_label == decision.decision_label:
            actions.append("answer with current decision label")

        return RiskDecision(
            final_label=final_label,
            risk_level=risk_level,
            safe_to_answer=safe_to_answer,
            total_risk_cost=total_cost,
            unsupported_high_risk_claims=tuple(dict.fromkeys(unsupported_high_risk)),
            issues=tuple(dict.fromkeys(issues)),
            recommended_actions=tuple(dict.fromkeys(actions)),
        )


def _risk_level(total_cost: int) -> str:
    if total_cost >= 10:
        return "critical"
    if total_cost >= 5:
        return "high"
    if total_cost >= 3:
        return "medium"
    return "low"


def _recommended_label(current_label: str, risk_level: str, unsupported_high_risk: list[str]) -> str:
    if not unsupported_high_risk:
        return current_label
    if risk_level == "critical":
        return "needs_owner_review"
    if "exact_product" in unsupported_high_risk and current_label == "confirmed_exact":
        return "likely_same_design"
    if "size_stock" in unsupported_high_risk:
        return "missing_fact"
    if "color_availability" in unsupported_high_risk:
        return "similar_style"
    return "no_confident_match"
