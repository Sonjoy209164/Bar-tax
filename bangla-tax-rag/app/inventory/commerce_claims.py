"""Typed commerce claim contracts for CIF-RAG.

Every customer-facing statement should map to a claim type with explicit
evidence requirements. This module does not write prose; it tells the decision
layer which claims are supported, missing, or unsafe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.inventory.counterfactual_planner import CounterfactualPlan
from app.inventory.image_matcher import ImageSearchDecision
from app.inventory.product_factor_graph import ProductFactorGraph


ClaimType = Literal[
    "exact_product",
    "same_design_variant",
    "similar_style",
    "color_availability",
    "size_stock",
    "price",
    "absence",
    "source_trust",
]


@dataclass(frozen=True)
class CommerceClaim:
    claim_type: ClaimType
    subject_product_id: str | None
    text: str
    required_evidence: tuple[str, ...]
    supported: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    risk_level: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_type": self.claim_type,
            "subject_product_id": self.subject_product_id,
            "text": self.text,
            "required_evidence": list(self.required_evidence),
            "supported": self.supported,
            "evidence": self.evidence,
            "missing_evidence": list(self.missing_evidence),
            "risk_level": self.risk_level,
        }


@dataclass(frozen=True)
class ClaimContractResult:
    claims: tuple[CommerceClaim, ...]
    unsupported_claims: tuple[CommerceClaim, ...]
    supported_claims: tuple[CommerceClaim, ...]
    claim_evidence_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [claim.to_dict() for claim in self.claims],
            "unsupported_claims": [claim.to_dict() for claim in self.unsupported_claims],
            "supported_claims": [claim.to_dict() for claim in self.supported_claims],
            "claim_evidence_coverage": self.claim_evidence_coverage,
        }


class CommerceClaimCompiler:
    """Compile a CIF plan and image decision into evidence-bound claims."""

    def __init__(self, graph: ProductFactorGraph) -> None:
        self.graph = graph

    def compile(
        self,
        *,
        plan: CounterfactualPlan,
        decision: ImageSearchDecision,
    ) -> ClaimContractResult:
        claims: list[CommerceClaim] = []
        primary_id = decision.primary_product_id
        primary = self.graph.product(primary_id)

        if decision.decision_label == "confirmed_exact":
            claims.append(self._exact_product_claim(primary_id))
        elif decision.decision_label in {"confirmed_same_design_variant", "likely_same_design"}:
            claims.append(self._same_design_claim(primary_id, decision))
        elif decision.decision_label == "similar_style":
            claims.append(self._similar_style_claim(primary_id, decision))

        if plan.requested_color or decision.requested_color:
            claims.append(self._color_availability_claim(primary_id, decision))

        if plan.requested_size or decision.requested_size:
            claims.append(self._size_stock_claim(primary_id, plan.requested_size or decision.requested_size))

        if primary and primary.price is not None:
            claims.append(self._price_claim(primary_id))

        claims.append(self._source_trust_claim(primary_id))

        supported = tuple(claim for claim in claims if claim.supported)
        unsupported = tuple(claim for claim in claims if not claim.supported)
        coverage = len(supported) / len(claims) if claims else 1.0
        return ClaimContractResult(
            claims=tuple(claims),
            unsupported_claims=unsupported,
            supported_claims=supported,
            claim_evidence_coverage=coverage,
        )

    def _exact_product_claim(self, product_id: str | None) -> CommerceClaim:
        node = self.graph.product(product_id)
        required = ("product_id", "product_photo", "stock_status")
        supported = bool(node and node.can_confirm_exact and node.stock >= 0)
        missing = _missing(
            {
                "product_id": bool(node),
                "product_photo": bool(node and node.can_confirm_exact),
                "stock_status": bool(node),
            }
        )
        return CommerceClaim(
            claim_type="exact_product",
            subject_product_id=product_id,
            text="Product can be claimed as exact same SKU.",
            required_evidence=required,
            supported=supported,
            evidence=self._product_evidence(product_id),
            missing_evidence=missing,
            risk_level="high",
        )

    def _same_design_claim(self, product_id: str | None, decision: ImageSearchDecision) -> CommerceClaim:
        node = self.graph.product(product_id)
        required = ("variant_group_id_or_design_id", "same_design_variants")
        siblings = self.graph.same_design_siblings(product_id, include_self=False)
        supported = bool(node and (node.variant_group_id or node.design_id) and siblings)
        missing = _missing(
            {
                "variant_group_id_or_design_id": bool(node and (node.variant_group_id or node.design_id)),
                "same_design_variants": bool(siblings or decision.same_design_variant_ids),
            }
        )
        return CommerceClaim(
            claim_type="same_design_variant",
            subject_product_id=product_id,
            text="Same-design variant relationship is supported by catalog identity.",
            required_evidence=required,
            supported=supported,
            evidence={
                **self._product_evidence(product_id),
                "same_design_variant_ids": list(decision.same_design_variant_ids),
            },
            missing_evidence=missing,
            risk_level="high",
        )

    def _similar_style_claim(self, product_id: str | None, decision: ImageSearchDecision) -> CommerceClaim:
        supported = bool(decision.hits)
        return CommerceClaim(
            claim_type="similar_style",
            subject_product_id=product_id,
            text="Visually or categorically similar alternatives are available.",
            required_evidence=("retrieved_hits",),
            supported=supported,
            evidence={
                "hit_count": len(decision.hits),
                "retrieved_product_ids": [hit.product_id for hit in decision.hits],
            },
            missing_evidence=() if supported else ("retrieved_hits",),
            risk_level="medium",
        )

    def _color_availability_claim(self, product_id: str | None, decision: ImageSearchDecision) -> CommerceClaim:
        requested_color = decision.requested_color
        available_colors = list(decision.available_colors)
        color_variants = self.graph.find_color_variant(product_id, requested_color)
        color_exists = bool(color_variants)
        requested_available = any(node.stock > 0 for node in color_variants)
        absence_supported = bool(requested_color and available_colors and requested_color not in available_colors)
        supported = bool((requested_color and requested_available) or absence_supported)
        missing = _missing(
            {
                "requested_color": bool(requested_color),
                "variant_group_checked": bool(available_colors),
                "stock_status": bool(requested_available or absence_supported),
            }
        )
        claim_type: ClaimType = "absence" if absence_supported and not requested_available else "color_availability"
        return CommerceClaim(
            claim_type=claim_type,
            subject_product_id=product_id,
            text="Requested color availability or absence is grounded in variant group evidence.",
            required_evidence=("requested_color", "variant_group_checked", "stock_status"),
            supported=supported,
            evidence={
                "requested_color": requested_color,
                "available_colors": available_colors,
                "matching_color_variant_ids": [node.product_id for node in color_variants],
                "requested_color_in_stock": requested_available,
            },
            missing_evidence=missing,
            risk_level="high",
        )

    def _size_stock_claim(self, product_id: str | None, requested_size: str | None) -> CommerceClaim:
        availability = self.graph.size_availability(product_id, requested_size)
        supported = bool(availability and availability.known)
        return CommerceClaim(
            claim_type="size_stock",
            subject_product_id=product_id,
            text="Requested size stock is checked against catalog size_stock.",
            required_evidence=("requested_size", "size_stock"),
            supported=supported,
            evidence=availability.__dict__ if availability else {"requested_size": requested_size},
            missing_evidence=() if supported else ("size_stock",),
            risk_level="high",
        )

    def _price_claim(self, product_id: str | None) -> CommerceClaim:
        node = self.graph.product(product_id)
        supported = bool(node and node.price is not None)
        return CommerceClaim(
            claim_type="price",
            subject_product_id=product_id,
            text="Product price is available in catalog.",
            required_evidence=("price", "currency"),
            supported=supported,
            evidence={"price": node.price, "currency": node.currency} if node else {},
            missing_evidence=() if supported else ("price",),
            risk_level="high",
        )

    def _source_trust_claim(self, product_id: str | None) -> CommerceClaim:
        node = self.graph.product(product_id)
        supported = bool(node and node.image_trust_level != "missing")
        return CommerceClaim(
            claim_type="source_trust",
            subject_product_id=product_id,
            text="Image source trust level is known.",
            required_evidence=("image_trust_level",),
            supported=supported,
            evidence={
                "image_kind": node.image_kind,
                "image_is_reference": node.image_is_reference,
                "image_trust_level": node.image_trust_level,
                "can_confirm_exact": node.can_confirm_exact,
            } if node else {},
            missing_evidence=() if supported else ("image_trust_level",),
            risk_level="medium",
        )

    def _product_evidence(self, product_id: str | None) -> dict[str, Any]:
        evidence = self.graph.evidence_for_product(product_id)
        if evidence is None:
            return {}
        return {
            "identity": evidence.identity,
            "business_state": evidence.business_state,
            "image_evidence": evidence.image_evidence,
            "variant_siblings": evidence.variant_siblings,
            "available_colors": evidence.available_colors,
        }


def _missing(checks: dict[str, bool]) -> tuple[str, ...]:
    return tuple(key for key, ok in checks.items() if not ok)
