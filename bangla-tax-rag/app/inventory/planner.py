from __future__ import annotations

from typing import Any

from app.core.schemas import InventoryAnswerPlan, InventoryEvidenceContract, InventoryProductEvidence
from app.inventory.intent import InventoryIntentResult
from app.inventory.ontology import ProductOntology
from app.inventory.preferences import InventoryPreferenceProfile
from app.inventory.tradeoffs import InventoryTradeoffReasoner


class InventoryAnswerPlanner:
    """Builds the explicit decision plan used before natural answer generation."""

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()
        self.tradeoff_reasoner = InventoryTradeoffReasoner(self.ontology)

    def enrich_plan(
        self,
        *,
        answer_plan: InventoryAnswerPlan,
        evidence_contract: InventoryEvidenceContract,
        intent_result: InventoryIntentResult,
        preferences: InventoryPreferenceProfile,
        strategy: str | None,
        next_best_question: str | None,
    ) -> InventoryAnswerPlan:
        plan_intent = answer_plan.intent if answer_plan.intent != "unknown" else intent_result.intent
        decision_strategy = self._decision_strategy(intent=plan_intent, strategy=strategy)
        resolved_plan, enriched_contract = self._apply_deterministic_decision(
            answer_plan=answer_plan,
            evidence_contract=evidence_contract,
            decision_strategy=decision_strategy,
        )
        candidate_by_id = {candidate.product_id: candidate for candidate in enriched_contract.candidate_evidence}
        primary = candidate_by_id.get(resolved_plan.primary_product_id or "")
        alternatives = [
            candidate_by_id[product_id]
            for product_id in resolved_plan.alternative_product_ids
            if product_id in candidate_by_id
        ]
        cross_sells = [
            candidate_by_id[product_id]
            for product_id in resolved_plan.cross_sell_product_ids
            if product_id in candidate_by_id
        ]

        confidence_breakdown = self._build_confidence_breakdown(
            primary=primary,
            alternatives=alternatives,
            cross_sells=cross_sells,
            intent_result=intent_result,
            preferences=preferences,
            decision_strategy=decision_strategy,
        )
        primary_reason = self._build_primary_reason(primary, preferences, decision_strategy)
        alternative_reason = self._build_alternative_reason(primary, alternatives, decision_strategy)
        cross_sell_reason = self._build_cross_sell_reason(primary, cross_sells)
        tradeoffs = self._build_tradeoffs(
            primary=primary,
            alternatives=alternatives,
            cross_sells=cross_sells,
            preferences=preferences,
        )
        risk_notes = self._build_risk_notes(
            answer_plan=resolved_plan,
            primary=primary,
            evidence_contract=enriched_contract,
            preferences=preferences,
            decision_strategy=decision_strategy,
        )
        resolved_next_question = next_best_question or self._build_next_best_question(
            intent=plan_intent,
            preferences=preferences,
            primary=primary,
        )

        reasoning_steps = list(resolved_plan.reasoning_steps)
        decision_steps = self._build_decision_reasoning_steps(
            primary=primary,
            alternatives=alternatives,
            decision_strategy=decision_strategy,
        )
        for step in decision_steps:
            reasoning_steps = self._append_unique(reasoning_steps, step)
        if primary_reason:
            reasoning_steps = self._append_unique(reasoning_steps, primary_reason)
        if alternative_reason:
            reasoning_steps = self._append_unique(reasoning_steps, alternative_reason)
        if cross_sell_reason:
            reasoning_steps = self._append_unique(reasoning_steps, cross_sell_reason)

        contract_follow_up_rules = list(enriched_contract.follow_up_question_rules)
        if resolved_next_question:
            contract_follow_up_rules = self._append_unique(contract_follow_up_rules, resolved_next_question)
        enriched_contract = enriched_contract.model_copy(
            update={"required_tradeoffs": tradeoffs, "follow_up_question_rules": contract_follow_up_rules}
        )

        return resolved_plan.model_copy(
            update={
                "intent": plan_intent,
                "detected_intent": intent_result.intent,
                "intent_confidence": intent_result.confidence,
                "intent_reasons": list(intent_result.reasons),
                "strategy": strategy if strategy != plan_intent else resolved_plan.strategy,
                "preferences": preferences.to_plan_dict(),
                "product_type": preferences.product_type,
                "product_family": preferences.product_family,
                "primary_reason": primary_reason,
                "alternative_reason": alternative_reason,
                "cross_sell_reason": cross_sell_reason,
                "tradeoffs": tradeoffs,
                "risk_notes": risk_notes,
                "next_best_question": resolved_next_question,
                "confidence_breakdown": confidence_breakdown,
                "reasoning_steps": reasoning_steps,
                "evidence_contract": enriched_contract,
            }
        )

    def _build_primary_reason(
        self,
        primary: InventoryProductEvidence | None,
        preferences: InventoryPreferenceProfile,
        decision_strategy: str | None,
    ) -> str | None:
        if primary is None:
            return None
        decision_score = self._decision_score(primary, decision_strategy)
        decision_reasons = self._decision_reasons(primary, decision_strategy)
        if decision_score is not None and decision_reasons:
            lead = "Primary restock candidate is" if decision_strategy == "restock" else "Primary recommendation is"
            return (
                f"{lead} {primary.name} because it leads the {self._decision_label(decision_strategy)} at "
                f"{decision_score:.2f} for {self._natural_reason_join(decision_reasons[:3])}."
            )
        evidence_reasons = self._evidence_reasons(primary)
        if evidence_reasons:
            return f"Primary recommendation is {primary.name} because " + "; ".join(evidence_reasons[:4]) + "."
        if preferences.product_type:
            return f"Primary recommendation is {primary.name} because it is the strongest ranked match for {preferences.product_type}."
        return f"Primary recommendation is {primary.name} because it is the strongest ranked catalog match."

    def _build_alternative_reason(
        self,
        primary: InventoryProductEvidence | None,
        alternatives: list[InventoryProductEvidence],
        decision_strategy: str | None,
    ) -> str | None:
        if primary is None or not alternatives:
            return None
        alternative = alternatives[0]
        relationship = self.ontology.explain_relationship(primary, alternative)
        price_note = self._price_relationship(primary, alternative)
        parts = [f"Alternative is {alternative.name} because {relationship}"]
        decision_score = self._decision_score(alternative, decision_strategy)
        decision_reasons = self._decision_reasons(alternative, decision_strategy)
        if decision_score is not None and decision_reasons:
            parts.append(
                f"it follows on the {self._decision_label(decision_strategy)} at {decision_score:.2f} for {self._natural_reason_join(decision_reasons[:2])}"
            )
        if price_note:
            parts.append(price_note)
        evidence_reasons = self._evidence_reasons(alternative)
        if evidence_reasons:
            parts.append("it also has " + "; ".join(evidence_reasons[:2]))
        return " ".join(parts).rstrip(".") + "."

    def _build_cross_sell_reason(
        self,
        primary: InventoryProductEvidence | None,
        cross_sells: list[InventoryProductEvidence],
    ) -> str | None:
        if primary is None or not cross_sells:
            return None
        cross_sell = cross_sells[0]
        relationship = self.ontology.explain_relationship(primary, cross_sell)
        reasons = self._evidence_reasons(cross_sell)
        if reasons:
            return f"Cross-sell is {cross_sell.name} because {relationship} " + "; ".join(reasons[:2]) + "."
        return f"Cross-sell is {cross_sell.name} because {relationship}"

    def _build_tradeoffs(
        self,
        *,
        primary: InventoryProductEvidence | None,
        alternatives: list[InventoryProductEvidence],
        cross_sells: list[InventoryProductEvidence],
        preferences: InventoryPreferenceProfile,
    ) -> list[str]:
        return self.tradeoff_reasoner.build_tradeoffs(
            primary=primary,
            alternatives=alternatives,
            cross_sells=cross_sells,
            preferences=preferences,
        )

    def _build_risk_notes(
        self,
        *,
        answer_plan: InventoryAnswerPlan,
        primary: InventoryProductEvidence | None,
        evidence_contract: InventoryEvidenceContract,
        preferences: InventoryPreferenceProfile,
        decision_strategy: str | None,
    ) -> list[str]:
        risk_notes: list[str] = []
        if answer_plan.abstain:
            risk_notes.append(answer_plan.abstention_reason or "The plan abstains because evidence is weak.")
        if not evidence_contract.candidate_evidence:
            risk_notes.append("No retrieved catalog evidence is available for this answer.")
        if primary is None and evidence_contract.candidate_evidence:
            risk_notes.append("No primary product was selected even though retrieval returned candidates.")
        risk_notes.extend(evidence_contract.missing_facts[:3])
        risk_notes.extend(evidence_contract.contradictions[:2])
        if primary is not None:
            final_score = self._evidence_number(primary, "final_score")
            if final_score is not None and final_score < 0.35:
                risk_notes.append(f"{primary.name} has a weak ecommerce fit score.")
            decision_score = self._decision_score(primary, decision_strategy)
            if decision_score is not None and decision_score < 0.45:
                risk_notes.append(f"{primary.name} only has a moderate {self._decision_label(decision_strategy)}.")
            if self._fact_value(primary, "price") is None:
                risk_notes.append(f"{primary.name} has no listed price.")
            stock_fact = self._fact(primary, "stock")
            if stock_fact is None or stock_fact.status == "missing":
                risk_notes.append(f"{primary.name} has no listed stock quantity.")
            if stock_fact is not None and stock_fact.status == "conflicting":
                risk_notes.append(f"{primary.name} has conflicting stock data across catalog and business snapshot.")
            if preferences.product_type:
                primary_type = self.ontology.detect_product_type(product=primary)
                if primary_type and primary_type != preferences.product_type:
                    risk_notes.append(
                        f"{primary.name} is a {primary_type}, not an exact {preferences.product_type} match."
                    )
        return self._dedupe(risk_notes)[:6]

    def _build_confidence_breakdown(
        self,
        *,
        primary: InventoryProductEvidence | None,
        alternatives: list[InventoryProductEvidence],
        cross_sells: list[InventoryProductEvidence],
        intent_result: InventoryIntentResult,
        preferences: InventoryPreferenceProfile,
        decision_strategy: str | None,
    ) -> dict[str, Any]:
        breakdown: dict[str, Any] = {
            "intent": {
                "label": intent_result.intent,
                "confidence": intent_result.confidence,
            },
            "preferences": {
                "confidence": preferences.confidence,
                "product_type": preferences.product_type,
                "product_family": preferences.product_family,
                "budget_min": preferences.budget_min,
                "budget_max": preferences.budget_max,
                "quality_level": preferences.quality_level,
            },
            "decision": {
                "strategy": decision_strategy,
            },
        }
        if primary is not None:
            breakdown["primary"] = self._score_summary(primary)
        if alternatives:
            breakdown["alternative"] = self._score_summary(alternatives[0])
        if cross_sells:
            breakdown["cross_sell"] = self._score_summary(cross_sells[0])
        if primary is not None:
            decision_score = self._decision_score(primary, decision_strategy)
            if decision_score is not None:
                breakdown["decision"]["primary_score"] = decision_score
        return breakdown

    def _build_next_best_question(
        self,
        *,
        intent: str,
        preferences: InventoryPreferenceProfile,
        primary: InventoryProductEvidence | None,
    ) -> str | None:
        if intent in {"small_talk", "support_no_match", "sales_no_match"}:
            return "What product type, category, budget, or brand should I focus on?"
        if preferences.budget_max is None and intent in {"recommendation", "product_search", "sales_general", "sales_premium"}:
            return "What budget range should I optimize for?"
        if not preferences.use_cases and primary is not None:
            return f"What will the customer use {primary.name} for?"
        if primary is not None:
            return f"Do you want a cheaper fallback, a premium step-up, or an add-on for {primary.name}?"
        return None

    def _score_summary(self, evidence: InventoryProductEvidence) -> dict[str, Any]:
        scores = evidence.score_breakdown or {}
        keys = (
            "final_score",
            "semantic_score",
            "lexical_score",
            "product_type_match",
            "family_match",
            "category_match",
            "price_fit",
            "stock_fit",
            "metadata_match",
            "structured_spec_match",
            "unrelated_category_penalty",
            "out_of_stock_penalty",
            "deterministic_recommendation_score",
            "deterministic_comparison_score",
            "deterministic_restock_score",
        )
        summary = {key: scores[key] for key in keys if key in scores}
        if scores.get("reasons"):
            summary["reasons"] = scores["reasons"]
        for strategy in ("recommendation", "comparison", "restock"):
            components = scores.get(f"deterministic_{strategy}_components")
            reasons = scores.get(f"deterministic_{strategy}_reasons")
            if isinstance(components, dict):
                summary[f"deterministic_{strategy}_components"] = components
            if isinstance(reasons, list):
                summary[f"deterministic_{strategy}_reasons"] = reasons
        return summary

    def _decision_strategy(self, *, intent: str, strategy: str | None) -> str | None:
        if strategy in {"comparison", "compare"} or intent == "comparison":
            return "comparison"
        if strategy == "restock" or "restock" in intent:
            return "restock"
        if intent in {
            "recommendation",
            "product_search",
            "sales_general",
            "sales_budget",
            "sales_premium",
            "sales_availability",
            "sales_urgency",
        } or (strategy and "sales" in strategy):
            return "recommendation"
        return None

    def _apply_deterministic_decision(
        self,
        *,
        answer_plan: InventoryAnswerPlan,
        evidence_contract: InventoryEvidenceContract,
        decision_strategy: str | None,
    ) -> tuple[InventoryAnswerPlan, InventoryEvidenceContract]:
        if decision_strategy is None or not evidence_contract.candidate_evidence:
            return answer_plan, evidence_contract
        ranked_candidates = self._rank_candidates_for_decision(
            candidates=evidence_contract.candidate_evidence,
            decision_strategy=decision_strategy,
        )
        if not ranked_candidates:
            return answer_plan, evidence_contract
        primary = ranked_candidates[0]
        alternatives = self._select_alternatives_for_decision(
            primary=primary,
            candidates=ranked_candidates[1:],
            decision_strategy=decision_strategy,
        )
        alternative_ids = [candidate.product_id for candidate in alternatives[:2]]
        primary_candidate_ids = [primary.product_id, *alternative_ids]
        role_by_id = {
            candidate.product_id: (
                "primary"
                if candidate.product_id == primary.product_id
                else "alternative"
                if candidate.product_id in alternative_ids
                else candidate.role
                if candidate.role in {"cross_sell", "rejected"}
                else "candidate"
            )
            for candidate in evidence_contract.candidate_evidence
        }
        updated_candidates = [
            candidate.model_copy(update={"role": role_by_id.get(candidate.product_id, candidate.role)})
            for candidate in evidence_contract.candidate_evidence
        ]
        updated_contract = evidence_contract.model_copy(
            update={
                "primary_product_id": primary.product_id,
                "primary_candidate_ids": primary_candidate_ids,
                "candidate_evidence": updated_candidates,
            }
        )
        updated_plan = answer_plan.model_copy(
            update={
                "primary_product_id": primary.product_id,
                "alternative_product_ids": alternative_ids,
            }
        )
        return updated_plan, updated_contract

    def _rank_candidates_for_decision(
        self,
        *,
        candidates: list[InventoryProductEvidence],
        decision_strategy: str,
    ) -> list[InventoryProductEvidence]:
        eligible = [candidate for candidate in candidates if candidate.role != "rejected"]
        return sorted(
            eligible,
            key=lambda candidate: (
                -(self._decision_score(candidate, decision_strategy) or 0.0),
                -(self._evidence_number(candidate, "final_score") or candidate.score or 0.0),
                candidate.name.casefold(),
            ),
        )

    def _select_alternatives_for_decision(
        self,
        *,
        primary: InventoryProductEvidence,
        candidates: list[InventoryProductEvidence],
        decision_strategy: str,
    ) -> list[InventoryProductEvidence]:
        if decision_strategy == "comparison":
            related = [candidate for candidate in candidates if self.ontology.valid_alternative(primary, candidate)]
            return related or candidates[:1]
        if decision_strategy == "recommendation":
            related = [candidate for candidate in candidates if self.ontology.valid_alternative(primary, candidate)]
            return related[:2]
        return []

    def _build_decision_reasoning_steps(
        self,
        *,
        primary: InventoryProductEvidence | None,
        alternatives: list[InventoryProductEvidence],
        decision_strategy: str | None,
    ) -> list[str]:
        if primary is None or decision_strategy is None:
            return []
        steps: list[str] = []
        primary_score = self._decision_score(primary, decision_strategy)
        primary_reasons = self._decision_reasons(primary, decision_strategy)
        if primary_score is not None and primary_reasons:
            steps.append(
                f"Deterministic {decision_strategy} scoring put {primary.name} first at {primary_score:.2f} using {self._natural_reason_join(primary_reasons[:3])}."
            )
        if alternatives:
            alternative = alternatives[0]
            alternative_score = self._decision_score(alternative, decision_strategy)
            alternative_reasons = self._decision_reasons(alternative, decision_strategy)
            if alternative_score is not None and alternative_reasons:
                steps.append(
                    f"Next-best option was {alternative.name} at {alternative_score:.2f} because {self._natural_reason_join(alternative_reasons[:2])}."
                )
        return steps

    @staticmethod
    def _decision_label(decision_strategy: str | None) -> str:
        if decision_strategy == "restock":
            return "restock scorecard"
        if decision_strategy == "comparison":
            return "comparison scorecard"
        return "recommendation scorecard"

    @staticmethod
    def _natural_reason_join(reasons: list[str]) -> str:
        if not reasons:
            return "stronger support"
        if len(reasons) == 1:
            return reasons[0]
        if len(reasons) == 2:
            return f"{reasons[0]} and {reasons[1]}"
        return ", ".join(reasons[:-1]) + f", and {reasons[-1]}"

    def _decision_score(self, evidence: InventoryProductEvidence, decision_strategy: str | None) -> float | None:
        if decision_strategy is None:
            return None
        value = evidence.score_breakdown.get(f"deterministic_{decision_strategy}_score") if evidence.score_breakdown else None
        return float(value) if isinstance(value, (int, float)) else None

    def _decision_reasons(self, evidence: InventoryProductEvidence, decision_strategy: str | None) -> list[str]:
        if decision_strategy is None or not evidence.score_breakdown:
            return []
        value = evidence.score_breakdown.get(f"deterministic_{decision_strategy}_reasons")
        if isinstance(value, list):
            return [reason for reason in value if isinstance(reason, str) and reason]
        return []

    @staticmethod
    def _evidence_reasons(evidence: InventoryProductEvidence) -> list[str]:
        return list(evidence.inclusion_reasons)

    def _price_relationship(self, primary: InventoryProductEvidence, candidate: InventoryProductEvidence) -> str | None:
        primary_price = self._fact_value(primary, "price")
        candidate_price = self._fact_value(candidate, "price")
        if primary_price is None or candidate_price is None:
            return None
        if candidate_price < primary_price:
            return f"it is cheaper than {primary.name} at {self._format_price(candidate)} versus {self._format_price(primary)}"
        if candidate_price > primary_price:
            return f"it is a step-up from {primary.name} at {self._format_price(candidate)} versus {self._format_price(primary)}"
        return f"it is priced the same as {primary.name} at {self._format_price(candidate)}"

    def _format_price(self, evidence: InventoryProductEvidence) -> str:
        price = self._fact_value(evidence, "price")
        currency = self._fact_unit(evidence, "price") or "USD"
        if price is None:
            return "price not listed"
        return f"{currency} {price:.2f}"

    @staticmethod
    def _evidence_number(evidence: InventoryProductEvidence, key: str) -> float | None:
        value = evidence.score_breakdown.get(key) if evidence.score_breakdown else None
        return float(value) if isinstance(value, (int, float)) else None

    @staticmethod
    def _append_unique(values: list[str], value: str) -> list[str]:
        if value not in values:
            values.append(value)
        return values

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    @staticmethod
    def _fact(evidence: InventoryProductEvidence, key: str):
        for fact in evidence.facts:
            if fact.key == key:
                return fact
        return None

    def _fact_value(self, evidence: InventoryProductEvidence, key: str) -> Any | None:
        fact = self._fact(evidence, key)
        return fact.value if fact is not None and fact.status == "present" else None

    def _fact_unit(self, evidence: InventoryProductEvidence, key: str) -> str | None:
        fact = self._fact(evidence, key)
        return fact.unit if fact is not None else None
