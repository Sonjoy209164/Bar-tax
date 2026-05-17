"""Counterfactual query planner for CIF-RAG.

The planner converts customer language into explicit product-identity
operations. It is intentionally deterministic first: research novelty comes
from the architecture and measurable contracts, not from hiding decisions in
an opaque prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.inventory.image_matcher import infer_requested_color, infer_requested_size


OperationName = Literal["IDENTIFY", "HOLD", "INTERVENE", "VERIFY", "RELAX", "ABSTAIN"]


@dataclass(frozen=True)
class CounterfactualOperation:
    op: OperationName
    target: str
    value: str | None = None
    source: str = "rule"
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "target": self.target,
            "value": self.value,
            "source": self.source,
            "required": self.required,
        }


@dataclass(frozen=True)
class CounterfactualPlan:
    query_text: str
    query_family: str
    answer_goal: str
    anchor_source: str
    requires_image_anchor: bool
    requested_color: str | None = None
    requested_size: str | None = None
    operations: tuple[CounterfactualOperation, ...] = field(default_factory=tuple)
    evidence_targets: tuple[str, ...] = field(default_factory=tuple)
    risk_notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_text": self.query_text,
            "query_family": self.query_family,
            "answer_goal": self.answer_goal,
            "anchor_source": self.anchor_source,
            "requires_image_anchor": self.requires_image_anchor,
            "requested_color": self.requested_color,
            "requested_size": self.requested_size,
            "operations": [operation.to_dict() for operation in self.operations],
            "evidence_targets": list(self.evidence_targets),
            "risk_notes": list(self.risk_notes),
        }


class CounterfactualQueryPlanner:
    """Compile customer turns into CIF-RAG operations."""

    def plan(
        self,
        *,
        query_text: str,
        has_image: bool,
        memory_anchor_product_id: str | None = None,
    ) -> CounterfactualPlan:
        text = query_text or ""
        normalized = _normalize_text(text)
        requested_color = infer_requested_color(text)
        requested_size = infer_requested_size(text)
        anchor_source = "image" if has_image else "memory" if memory_anchor_product_id else "text"
        operations: list[CounterfactualOperation] = [
            CounterfactualOperation(
                "IDENTIFY",
                "product_from_image" if has_image else "product_or_memory_anchor",
                value=memory_anchor_product_id,
                source=anchor_source,
            )
        ]
        risk_notes: list[str] = []

        if _has_color_listing_intent(normalized):
            query_family = "variant_color_listing"
            answer_goal = "list_same_design_colors"
            operations.extend(
                [
                    CounterfactualOperation("HOLD", "design"),
                    CounterfactualOperation("VERIFY", "available_colors"),
                    CounterfactualOperation("VERIFY", "stock_status"),
                ]
            )
            evidence_targets = ("variant_group_id", "design_id", "color", "stock")
        elif requested_color and _has_same_design_intent(normalized):
            query_family = "same_design_color_intervention"
            answer_goal = "find_requested_color_variant"
            operations.extend(
                [
                    CounterfactualOperation("HOLD", "design"),
                    CounterfactualOperation("INTERVENE", "color", value=requested_color),
                    CounterfactualOperation("VERIFY", "variant_exists"),
                    CounterfactualOperation("VERIFY", "stock_status"),
                ]
            )
            evidence_targets = ("variant_group_id", "design_id", "requested_color", "stock")
        elif requested_color and _has_availability_intent(normalized):
            query_family = "color_availability"
            answer_goal = "verify_requested_color"
            operations.extend(
                [
                    CounterfactualOperation("HOLD", "design", required=False),
                    CounterfactualOperation("INTERVENE", "color", value=requested_color),
                    CounterfactualOperation("VERIFY", "variant_exists"),
                    CounterfactualOperation("VERIFY", "stock_status"),
                ]
            )
            evidence_targets = ("color", "variant_group_id", "stock")
        elif requested_size:
            query_family = "size_availability"
            answer_goal = "verify_size_stock"
            operations.extend(
                [
                    CounterfactualOperation("VERIFY", "size", value=requested_size),
                    CounterfactualOperation("VERIFY", "size_stock"),
                ]
            )
            evidence_targets = ("size_stock", "stock", "status")
        elif _has_similar_intent(normalized):
            query_family = "similar_style_search"
            answer_goal = "recommend_similar_available_items"
            operations.extend(
                [
                    CounterfactualOperation("RELAX", "product_id"),
                    CounterfactualOperation("HOLD", "category", required=False),
                    CounterfactualOperation("HOLD", "style_or_design", required=False),
                    CounterfactualOperation("VERIFY", "stock_status"),
                ]
            )
            evidence_targets = ("category", "style", "stock")
        elif _has_exact_intent(normalized):
            query_family = "exact_product_check"
            answer_goal = "verify_exact_product_availability"
            operations.extend(
                [
                    CounterfactualOperation("VERIFY", "image_trust"),
                    CounterfactualOperation("VERIFY", "product_status"),
                    CounterfactualOperation("VERIFY", "stock_status"),
                ]
            )
            evidence_targets = ("product_id", "image_trust", "stock", "status")
        else:
            query_family = "open_image_search"
            answer_goal = "identify_or_recommend"
            operations.extend(
                [
                    CounterfactualOperation("HOLD", "category", required=False),
                    CounterfactualOperation("VERIFY", "stock_status"),
                ]
            )
            evidence_targets = ("category", "stock")

        if not has_image and not memory_anchor_product_id:
            risk_notes.append("no image or memory anchor; exact and same-design claims require stronger evidence")
            operations.append(CounterfactualOperation("ABSTAIN", "exact_identity_if_unresolved", required=False))

        return CounterfactualPlan(
            query_text=text,
            query_family=query_family,
            answer_goal=answer_goal,
            anchor_source=anchor_source,
            requires_image_anchor=has_image or bool(memory_anchor_product_id),
            requested_color=requested_color,
            requested_size=requested_size,
            operations=tuple(operations),
            evidence_targets=evidence_targets,
            risk_notes=tuple(risk_notes),
        )


def _normalize_text(text: str) -> str:
    return " ".join(text.casefold().replace("?", " ").replace("।", " ").split())


def _has_same_design_intent(text: str) -> bool:
    phrases = (
        "same design",
        "same pattern",
        "ei design",
        "e design",
        "ei same",
        "এই ডিজাইন",
        "একই ডিজাইন",
        "same color na",
    )
    return any(phrase in text for phrase in phrases)


def _has_color_listing_intent(text: str) -> bool:
    phrases = (
        "ki ki color",
        "ki color",
        "what color",
        "other color",
        "available color",
        "ar ki color",
        "আর কি কালার",
        "কী কী কালার",
    )
    return any(phrase in text for phrase in phrases)


def _has_availability_intent(text: str) -> bool:
    phrases = (
        "ache",
        "available",
        "stock",
        "আছে",
        "ase",
        "pabo",
        "can i get",
    )
    return any(phrase in text for phrase in phrases)


def _has_similar_intent(text: str) -> bool:
    phrases = (
        "similar",
        "moto",
        "এরকম",
        "ei rokom",
        "dekhan",
        "show",
        "alternative",
        "closest",
        "nearer",
    )
    return any(phrase in text for phrase in phrases)


def _has_exact_intent(text: str) -> bool:
    phrases = (
        "eta ache",
        "do you have this",
        "exact",
        "same product",
        "এইটা আছে",
        "এটা আছে",
        "apnader kase ache",
        "available",
    )
    return any(phrase in text for phrase in phrases) or not text.strip()
