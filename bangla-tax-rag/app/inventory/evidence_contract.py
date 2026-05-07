from __future__ import annotations

from collections.abc import Iterable

from app.core.schemas import (
    InventoryAnswerPlan,
    InventoryBusinessSignalRecord,
    InventoryEvidenceContract,
    InventoryFact,
    InventoryFactProvenance,
    InventoryProductEvidence,
    InventorySearchHit,
)
from app.inventory.ontology import ProductOntology, normalize_inventory_text
from app.inventory.preferences import InventoryPreferenceProfile
from app.inventory.spec_utils import normalized_spec_facts


class InventoryEvidenceContractBuilder:
    """Builds the normalized evidence package shared by planning and verification."""

    BUSINESS_QUESTION_HINTS = {
        "restock",
        "reorder",
        "stockout",
        "lead time",
        "lead-time",
        "demand",
        "margin",
        "profit",
        "supplier",
    }

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()

    def build(
        self,
        *,
        question: str,
        answer_plan: InventoryAnswerPlan,
        hits: list[InventorySearchHit],
        preferences: InventoryPreferenceProfile,
        business_signals: dict[str, InventoryBusinessSignalRecord] | None = None,
        next_best_question: str | None = None,
    ) -> InventoryEvidenceContract:
        business_signals = business_signals or {}
        selected_ids = self._selected_product_ids(answer_plan)
        primary_candidate_ids = [
            product_id
            for product_id in [
                answer_plan.primary_product_id,
                *answer_plan.alternative_product_ids,
                *answer_plan.cross_sell_product_ids,
            ]
            if product_id
        ]
        candidate_evidence: list[InventoryProductEvidence] = []
        contract_missing_facts: list[str] = []
        contract_contradictions: list[str] = []
        allowed_claims: list[str] = []

        question_text = normalize_inventory_text(question)
        requires_business_context = any(hint in question_text for hint in self.BUSINESS_QUESTION_HINTS)

        for hit in hits:
            business_signal = business_signals.get(hit.product_id)
            role = self._candidate_role(hit.product_id, answer_plan)
            candidate = self._build_candidate_evidence(
                hit=hit,
                role=role,
                preferences=preferences,
                business_signal=business_signal,
                requires_business_context=requires_business_context,
                primary_product_id=answer_plan.primary_product_id,
            )
            candidate_evidence.append(candidate)
            contract_missing_facts.extend(candidate.missing_facts)
            contract_contradictions.extend(candidate.contradictions)
            allowed_claims.extend(candidate.allowed_claims)

        if answer_plan.primary_product_id and answer_plan.primary_product_id not in {hit.product_id for hit in hits}:
            contract_missing_facts.append("Primary product evidence is missing from the retrieved candidate set.")

        follow_up_question_rules = self._build_follow_up_rules(
            preferences=preferences,
            next_best_question=next_best_question,
            missing_facts=contract_missing_facts,
        )

        return InventoryEvidenceContract(
            question=question,
            primary_product_id=answer_plan.primary_product_id,
            primary_candidate_ids=primary_candidate_ids,
            rejected_candidate_ids=[hit.product_id for hit in hits if hit.product_id not in selected_ids],
            candidate_evidence=candidate_evidence,
            missing_facts=self._dedupe(contract_missing_facts),
            contradictions=self._dedupe(contract_contradictions),
            allowed_claims=self._dedupe(allowed_claims),
            follow_up_question_rules=follow_up_question_rules,
        )

    def _build_candidate_evidence(
        self,
        *,
        hit: InventorySearchHit,
        role: str,
        preferences: InventoryPreferenceProfile,
        business_signal: InventoryBusinessSignalRecord | None,
        requires_business_context: bool,
        primary_product_id: str | None,
    ) -> InventoryProductEvidence:
        contradictions: list[str] = []
        missing_facts: list[str] = []
        inclusion_reasons = self._candidate_inclusion_reasons(hit, role=role, business_signal=business_signal)
        rejection_reasons = self._candidate_rejection_reasons(
            hit,
            role=role,
            primary_product_id=primary_product_id,
        )
        facts: list[InventoryFact] = []

        facts.append(
            self._simple_fact(
                key="price",
                value=hit.price,
                unit=hit.currency,
                source_type="catalog",
                source_field="price",
                source_updated_at=hit.updated_at,
                missing_note=f"{hit.name} has no listed price.",
                missing_facts=missing_facts,
            )
        )
        facts.append(self._stock_fact(hit=hit, business_signal=business_signal, contradictions=contradictions))
        facts.append(
            self._simple_fact(
                key="availability",
                value=self._availability_value(hit, business_signal),
                source_type="inferred",
                source_field="availability",
                source_updated_at=business_signal.inventory_snapshot_at if business_signal else hit.updated_at,
            )
        )
        facts.append(
            self._simple_fact(
                key="category",
                value=hit.category,
                source_type="catalog",
                source_field="category",
                source_updated_at=hit.updated_at,
            )
        )
        facts.append(
            self._simple_fact(
                key="brand",
                value=hit.brand,
                source_type="catalog",
                source_field="brand",
                source_updated_at=hit.updated_at,
            )
        )

        spec_facts = self._spec_facts(
            hit=hit,
            preferences=preferences,
            missing_facts=missing_facts,
        )
        facts.extend(spec_facts)

        if business_signal is not None:
            facts.extend(self._business_facts(hit=hit, signal=business_signal))
        elif requires_business_context and role == "primary":
            missing_facts.append(f"{hit.name} is missing business signal support for this operational question.")

        allowed_claims = self._allowed_claims(
            hit=hit,
            facts=facts,
            role=role,
            inclusion_reasons=inclusion_reasons,
        )

        return InventoryProductEvidence(
            product_id=hit.product_id,
            sku=hit.sku,
            name=hit.name,
            category=hit.category,
            brand=hit.brand,
            currency=hit.currency,
            price=hit.price,
            stock=hit.stock,
            tags=list(hit.tags),
            snippet=hit.snippet,
            role=role,
            score=hit.score,
            score_breakdown=dict(hit.evidence_scores),
            inclusion_reasons=inclusion_reasons,
            rejection_reasons=rejection_reasons,
            facts=facts,
            allowed_claims=allowed_claims,
            contradictions=self._dedupe(contradictions),
            missing_facts=self._dedupe(missing_facts),
        )

    def _simple_fact(
        self,
        *,
        key: str,
        value: object | None,
        source_type: str,
        source_field: str,
        source_updated_at: str | None,
        unit: str | None = None,
        missing_note: str | None = None,
        missing_facts: list[str] | None = None,
    ) -> InventoryFact:
        if value is None or value == "":
            if missing_note and missing_facts is not None:
                missing_facts.append(missing_note)
            return InventoryFact(
                key=key,
                value=None,
                status="missing",
                unit=unit,
                provenance=[
                    InventoryFactProvenance(
                        source_type=source_type,
                        source_field=source_field,
                        source_updated_at=source_updated_at,
                    )
                ],
            )
        return InventoryFact(
            key=key,
            value=value,
            status="present",
            unit=unit,
            provenance=[
                InventoryFactProvenance(
                    source_type=source_type,
                    source_field=source_field,
                    source_updated_at=source_updated_at,
                )
            ],
        )

    def _stock_fact(
        self,
        *,
        hit: InventorySearchHit,
        business_signal: InventoryBusinessSignalRecord | None,
        contradictions: list[str],
    ) -> InventoryFact:
        provenances = [
            InventoryFactProvenance(
                source_type="catalog",
                source_field="stock",
                source_updated_at=hit.updated_at,
            )
        ]
        catalog_stock = hit.stock
        snapshot_stock = business_signal.inventory_on_hand if business_signal else None
        if business_signal is not None:
            provenances.append(
                InventoryFactProvenance(
                    source_type="business_signal",
                    source_field="inventory_on_hand",
                    source_updated_at=business_signal.inventory_snapshot_at or business_signal.updated_at,
                )
            )

        if catalog_stock is None and snapshot_stock is None:
            return InventoryFact(key="stock", value=None, status="missing", provenance=provenances)
        if catalog_stock is not None and snapshot_stock is not None and catalog_stock != snapshot_stock:
            contradictions.append(
                f"{hit.name} has conflicting stock signals: catalog shows {catalog_stock} while business snapshot shows {snapshot_stock}."
            )
            return InventoryFact(
                key="stock",
                value={"catalog": catalog_stock, "business_snapshot": snapshot_stock},
                status="conflicting",
                provenance=provenances,
                notes=["Use caution when speaking about exact stock quantity."],
            )
        resolved_value = snapshot_stock if snapshot_stock is not None else catalog_stock
        return InventoryFact(
            key="stock",
            value=resolved_value,
            status="present",
            provenance=provenances,
        )

    def _spec_facts(
        self,
        *,
        hit: InventorySearchHit,
        preferences: InventoryPreferenceProfile,
        missing_facts: list[str],
    ) -> list[InventoryFact]:
        normalized_specs = self._normalized_specs(hit)
        facts: list[InventoryFact] = []
        if not normalized_specs:
            missing_facts.append(f"{hit.name} is missing structured specs.")
        for key, value in sorted(normalized_specs.items()):
            facts.append(
                InventoryFact(
                    key=f"spec.{key}",
                    value=value,
                    status="present",
                    provenance=[
                        InventoryFactProvenance(
                            source_type="catalog",
                            source_field=f"attributes.{key}",
                            source_updated_at=hit.updated_at,
                        )
                    ],
                )
            )

        for requirement in preferences.spec_requirements:
            normalized_key = requirement.key.casefold()
            if normalized_key not in normalized_specs:
                missing_facts.append(f"{hit.name} is missing required spec: {requirement.key}.")
        return facts

    def _business_facts(
        self,
        *,
        hit: InventorySearchHit,
        signal: InventoryBusinessSignalRecord,
    ) -> list[InventoryFact]:
        facts: list[InventoryFact] = []
        updated_at = signal.inventory_snapshot_at or signal.updated_at or signal.period_end
        facts.append(
            self._simple_fact(
                key="demand_score",
                value=signal.demand_score,
                source_type="business_signal",
                source_field="demand_score",
                source_updated_at=updated_at,
            )
        )
        facts.append(
            self._simple_fact(
                key="gross_margin_rate",
                value=signal.gross_margin_rate,
                unit="ratio",
                source_type="business_signal",
                source_field="gross_margin_rate",
                source_updated_at=updated_at,
            )
        )
        facts.append(
            self._simple_fact(
                key="supplier_lead_time_days",
                value=signal.supplier_lead_time_days,
                unit="days",
                source_type="business_signal",
                source_field="supplier_lead_time_days",
                source_updated_at=updated_at,
            )
        )
        facts.append(
            self._simple_fact(
                key="units_sold",
                value=signal.units_sold,
                unit="units",
                source_type="business_signal",
                source_field="units_sold",
                source_updated_at=updated_at,
            )
        )
        facts.append(
            self._simple_fact(
                key="inventory_snapshot_at",
                value=signal.inventory_snapshot_at,
                source_type="business_signal",
                source_field="inventory_snapshot_at",
                source_updated_at=updated_at,
            )
        )
        return facts

    def _candidate_inclusion_reasons(
        self,
        hit: InventorySearchHit,
        *,
        role: str,
        business_signal: InventoryBusinessSignalRecord | None,
    ) -> list[str]:
        reasons = [
            reason
            for reason in hit.evidence_scores.get("reasons", [])
            if isinstance(reason, str)
        ] if hit.evidence_scores else []
        if role == "primary":
            reasons.insert(0, "Selected as the lead candidate for the answer.")
        elif role == "alternative":
            reasons.insert(0, "Selected as a bounded alternative to the primary candidate.")
        elif role == "cross_sell":
            reasons.insert(0, "Selected as a complementary add-on, not a substitute.")
        if business_signal is not None:
            if business_signal.demand_score is not None:
                reasons.append(f"business demand score available: {business_signal.demand_score:.2f}")
            if business_signal.supplier_lead_time_days is not None:
                reasons.append(f"supplier lead time available: {business_signal.supplier_lead_time_days} day(s)")
            if business_signal.gross_margin_rate is not None:
                reasons.append(f"margin rate available: {business_signal.gross_margin_rate * 100:.1f}%")
        return self._dedupe(reasons)

    def _candidate_rejection_reasons(
        self,
        hit: InventorySearchHit,
        *,
        role: str,
        primary_product_id: str | None,
    ) -> list[str]:
        if role != "rejected":
            return []
        reasons = ["Retrieved but not selected into the final answer plan."]
        if primary_product_id and primary_product_id != hit.product_id:
            reasons.append("A stronger primary candidate was available.")
        if hit.evidence_scores.get("reasons"):
            reasons.append("Reranker support was weaker than the selected candidates.")
        return reasons

    def _allowed_claims(
        self,
        *,
        hit: InventorySearchHit,
        facts: list[InventoryFact],
        role: str,
        inclusion_reasons: list[str],
    ) -> list[str]:
        claims = [
            f"{hit.name} exists in the retrieved evidence.",
            f"{hit.name} has role {role}.",
        ]
        if hit.brand:
            claims.append(f"{hit.name} brand is {hit.brand}.")
        if hit.category:
            claims.append(f"{hit.name} category is {hit.category}.")
        for fact in facts:
            if fact.status != "present":
                continue
            if fact.key == "price":
                claims.append(f"{hit.name} price is {hit.currency or 'USD'} {float(fact.value):.2f}.")
            elif fact.key == "stock":
                claims.append(f"{hit.name} stock is {fact.value}.")
            elif fact.key == "demand_score":
                claims.append(f"{hit.name} demand score is {float(fact.value):.2f}.")
            elif fact.key == "gross_margin_rate":
                claims.append(f"{hit.name} margin rate is {float(fact.value) * 100:.1f}%.")
            elif fact.key == "supplier_lead_time_days":
                claims.append(f"{hit.name} supplier lead time is {int(fact.value)} day(s).")
            elif fact.key.startswith("spec."):
                claims.append(f"{hit.name} {fact.key.removeprefix('spec.').replace('_', ' ')} is {fact.value}.")
        claims.extend(inclusion_reasons[:4])
        return self._dedupe(claims)

    def _candidate_role(self, product_id: str, answer_plan: InventoryAnswerPlan) -> str:
        if answer_plan.primary_product_id == product_id:
            return "primary"
        if product_id in answer_plan.alternative_product_ids:
            return "alternative"
        if product_id in answer_plan.cross_sell_product_ids:
            return "cross_sell"
        return "rejected"

    @staticmethod
    def _selected_product_ids(answer_plan: InventoryAnswerPlan) -> set[str]:
        return {
            product_id
            for product_id in [
                answer_plan.primary_product_id,
                *answer_plan.alternative_product_ids,
                *answer_plan.cross_sell_product_ids,
            ]
            if product_id
        }

    def _build_follow_up_rules(
        self,
        *,
        preferences: InventoryPreferenceProfile,
        next_best_question: str | None,
        missing_facts: list[str],
    ) -> list[str]:
        rules: list[str] = []
        if next_best_question:
            rules.append(next_best_question)
        if preferences.budget_max is None and preferences.budget_min is None:
            rules.append("Ask for budget before making a stronger recommendation when price is still unconstrained.")
        if not preferences.use_cases:
            rules.append("Ask about intended use case when multiple coherent candidates remain.")
        if any("structured specs" in fact.casefold() for fact in missing_facts):
            rules.append("Ask which specs matter most when the catalog is missing structured specs.")
        return self._dedupe(rules)

    @staticmethod
    def _availability_value(hit: InventorySearchHit, business_signal: InventoryBusinessSignalRecord | None) -> str:
        if business_signal and business_signal.inventory_on_hand is not None:
            return "in_stock" if business_signal.inventory_on_hand > 0 else "out_of_stock"
        if hit.stock is None:
            return "unknown"
        return "in_stock" if hit.stock > 0 else "out_of_stock"

    @staticmethod
    def _normalized_specs(hit: InventorySearchHit) -> dict[str, object]:
        return normalized_spec_facts(attributes=hit.attributes, metadata=hit.metadata)

    @staticmethod
    def _dedupe(items: Iterable[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped
