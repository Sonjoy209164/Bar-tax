from __future__ import annotations

from typing import Any

from app.core.schemas import InventoryAnswerPlan, InventorySearchHit
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
        hits: list[InventorySearchHit],
        intent_result: InventoryIntentResult,
        preferences: InventoryPreferenceProfile,
        strategy: str | None,
        next_best_question: str | None,
    ) -> InventoryAnswerPlan:
        hit_by_id = {hit.product_id: hit for hit in hits}
        primary = hit_by_id.get(answer_plan.primary_product_id or "")
        alternatives = [
            hit_by_id[product_id]
            for product_id in answer_plan.alternative_product_ids
            if product_id in hit_by_id
        ]
        cross_sells = [
            hit_by_id[product_id]
            for product_id in answer_plan.cross_sell_product_ids
            if product_id in hit_by_id
        ]
        plan_intent = answer_plan.intent if answer_plan.intent != "unknown" else intent_result.intent

        confidence_breakdown = self._build_confidence_breakdown(
            primary=primary,
            alternatives=alternatives,
            cross_sells=cross_sells,
            intent_result=intent_result,
            preferences=preferences,
        )
        primary_reason = self._build_primary_reason(primary, preferences)
        alternative_reason = self._build_alternative_reason(primary, alternatives)
        cross_sell_reason = self._build_cross_sell_reason(primary, cross_sells)
        tradeoffs = self._build_tradeoffs(
            primary=primary,
            alternatives=alternatives,
            cross_sells=cross_sells,
            preferences=preferences,
        )
        risk_notes = self._build_risk_notes(
            answer_plan=answer_plan,
            primary=primary,
            hits=hits,
            preferences=preferences,
        )
        resolved_next_question = next_best_question or self._build_next_best_question(
            intent=plan_intent,
            preferences=preferences,
            primary=primary,
        )

        reasoning_steps = list(answer_plan.reasoning_steps)
        if primary_reason:
            reasoning_steps = self._append_unique(reasoning_steps, primary_reason)
        if alternative_reason:
            reasoning_steps = self._append_unique(reasoning_steps, alternative_reason)
        if cross_sell_reason:
            reasoning_steps = self._append_unique(reasoning_steps, cross_sell_reason)

        return answer_plan.model_copy(
            update={
                "intent": plan_intent,
                "detected_intent": intent_result.intent,
                "intent_confidence": intent_result.confidence,
                "intent_reasons": list(intent_result.reasons),
                "strategy": strategy if strategy != plan_intent else answer_plan.strategy,
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
            }
        )

    def _build_primary_reason(
        self,
        primary: InventorySearchHit | None,
        preferences: InventoryPreferenceProfile,
    ) -> str | None:
        if primary is None:
            return None
        evidence_reasons = self._evidence_reasons(primary)
        if evidence_reasons:
            return f"Primary recommendation is {primary.name} because " + "; ".join(evidence_reasons[:4]) + "."
        if preferences.product_type:
            return f"Primary recommendation is {primary.name} because it is the strongest ranked match for {preferences.product_type}."
        return f"Primary recommendation is {primary.name} because it is the strongest ranked catalog match."

    def _build_alternative_reason(
        self,
        primary: InventorySearchHit | None,
        alternatives: list[InventorySearchHit],
    ) -> str | None:
        if primary is None or not alternatives:
            return None
        alternative = alternatives[0]
        relationship = self.ontology.explain_relationship(primary, alternative)
        price_note = self._price_relationship(primary, alternative)
        parts = [f"Alternative is {alternative.name} because {relationship}"]
        if price_note:
            parts.append(price_note)
        evidence_reasons = self._evidence_reasons(alternative)
        if evidence_reasons:
            parts.append("it also has " + "; ".join(evidence_reasons[:2]))
        return " ".join(parts).rstrip(".") + "."

    def _build_cross_sell_reason(
        self,
        primary: InventorySearchHit | None,
        cross_sells: list[InventorySearchHit],
    ) -> str | None:
        if primary is None or not cross_sells:
            return None
        cross_sell = cross_sells[0]
        relationship = self.ontology.explain_relationship(primary, cross_sell)
        return f"Cross-sell is {cross_sell.name} because {relationship}"

    def _build_tradeoffs(
        self,
        *,
        primary: InventorySearchHit | None,
        alternatives: list[InventorySearchHit],
        cross_sells: list[InventorySearchHit],
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
        primary: InventorySearchHit | None,
        hits: list[InventorySearchHit],
        preferences: InventoryPreferenceProfile,
    ) -> list[str]:
        risk_notes: list[str] = []
        if answer_plan.abstain:
            risk_notes.append(answer_plan.abstention_reason or "The plan abstains because evidence is weak.")
        if not hits:
            risk_notes.append("No retrieved catalog evidence is available for this answer.")
        if primary is None and hits:
            risk_notes.append("No primary product was selected even though retrieval returned candidates.")
        if primary is not None:
            final_score = self._evidence_number(primary, "final_score")
            if final_score is not None and final_score < 0.35:
                risk_notes.append(f"{primary.name} has a weak ecommerce fit score.")
            if primary.price is None:
                risk_notes.append(f"{primary.name} has no listed price.")
            if primary.stock is None:
                risk_notes.append(f"{primary.name} has no listed stock quantity.")
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
        primary: InventorySearchHit | None,
        alternatives: list[InventorySearchHit],
        cross_sells: list[InventorySearchHit],
        intent_result: InventoryIntentResult,
        preferences: InventoryPreferenceProfile,
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
        }
        if primary is not None:
            breakdown["primary"] = self._score_summary(primary)
        if alternatives:
            breakdown["alternative"] = self._score_summary(alternatives[0])
        if cross_sells:
            breakdown["cross_sell"] = self._score_summary(cross_sells[0])
        return breakdown

    def _build_next_best_question(
        self,
        *,
        intent: str,
        preferences: InventoryPreferenceProfile,
        primary: InventorySearchHit | None,
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

    def _score_summary(self, hit: InventorySearchHit) -> dict[str, Any]:
        scores = hit.evidence_scores or {}
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
            "unrelated_category_penalty",
            "out_of_stock_penalty",
        )
        summary = {key: scores[key] for key in keys if key in scores}
        if scores.get("reasons"):
            summary["reasons"] = scores["reasons"]
        return summary

    def _evidence_reasons(self, hit: InventorySearchHit) -> list[str]:
        reasons = hit.evidence_scores.get("reasons") if hit.evidence_scores else None
        return [reason for reason in reasons if isinstance(reason, str)] if isinstance(reasons, list) else []

    def _price_relationship(self, primary: InventorySearchHit, candidate: InventorySearchHit) -> str | None:
        if primary.price is None or candidate.price is None:
            return None
        if candidate.price < primary.price:
            return f"it is cheaper than {primary.name} at {self._format_price(candidate)} versus {self._format_price(primary)}"
        if candidate.price > primary.price:
            return f"it is a step-up from {primary.name} at {self._format_price(candidate)} versus {self._format_price(primary)}"
        return f"it is priced the same as {primary.name} at {self._format_price(candidate)}"

    @staticmethod
    def _format_price(hit: InventorySearchHit) -> str:
        if hit.price is None:
            return "price not listed"
        return f"{hit.currency or 'USD'} {hit.price:.2f}"

    @staticmethod
    def _evidence_number(hit: InventorySearchHit, key: str) -> float | None:
        value = hit.evidence_scores.get(key) if hit.evidence_scores else None
        return float(value) if isinstance(value, int | float) else None

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
