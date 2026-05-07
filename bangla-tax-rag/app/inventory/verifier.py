from __future__ import annotations

import re
from itertools import combinations

from app.core.schemas import (
    InventoryAnswerPlan,
    InventoryAnswerVerification,
    InventoryEvidenceContract,
    InventoryProductEvidence,
    InventorySearchHit,
)
from app.inventory.ontology import ProductOntology, normalize_inventory_text
from app.inventory.preferences import InventorySpecRequirement
from app.inventory.spec_utils import (
    BOOLEAN_FALSE_VALUES,
    BOOLEAN_TRUE_VALUES,
    SPEC_METADATA_ALIASES,
    coerce_spec_bool,
    coerce_spec_number,
    spec_requirement_satisfied,
)


class InventoryFinalAnswerVerifier:
    """Checks the final user-facing text against the product evidence and plan."""

    SUSPICIOUS_UNSUPPORTED_CLAIMS = (
        "free shipping",
        "same day delivery",
        "next day delivery",
        "discount",
        "coupon",
        "lifetime warranty",
        "waterproof",
        "water resistant",
        "made in usa",
        "official apple",
        "certified refurbished",
    )
    RECOMMENDATION_WORDS = (
        "recommend",
        "recommended",
        "lead with",
        "start with",
        "pitch",
        "show",
        "sell",
        "fallback",
        "alternative",
        "substitute",
        "replacement",
        "switch to",
        "shift to",
        "go with",
    )
    SUBSTITUTE_WORDS = ("alternative", "fallback", "substitute", "replacement", "instead", "switch to", "shift to")
    CAVEAT_WORDS = ("fallback", "related", "nearby", "not exact", "not equivalent", "not a substitute", "not a replacement")
    NO_MATCH_WORDS = ("could not find", "no reliable", "no exact", "not enough evidence", "do not have")
    BOOLEAN_TRUE_VALUES = BOOLEAN_TRUE_VALUES
    BOOLEAN_FALSE_VALUES = BOOLEAN_FALSE_VALUES
    SPEC_METADATA_ALIASES = SPEC_METADATA_ALIASES

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()

    def verify(
        self,
        *,
        answer: str,
        answer_plan: InventoryAnswerPlan,
        hits: list[InventorySearchHit],
    ) -> InventoryAnswerVerification:
        normalized_answer = normalize_inventory_text(answer)
        hit_by_id = {hit.product_id: hit for hit in hits}
        contract = answer_plan.evidence_contract
        issues: list[str] = []

        issues.extend(self._check_excluded_products(normalized_answer, answer_plan, hit_by_id))
        issues.extend(self._check_invented_product_names(answer, hits))
        issues.extend(self._check_primary_product_grounding(normalized_answer, answer_plan, hit_by_id))
        issues.extend(self._check_prices(answer, hits, contract))
        issues.extend(self._check_stock(answer, hits, contract))
        issues.extend(self._check_unsupported_claims(normalized_answer, contract, hits))
        issues.extend(self._check_abstention(normalized_answer, answer_plan))
        issues.extend(self._check_cross_sell_boundary(normalized_answer, answer_plan, hit_by_id))
        issues.extend(self._check_near_alternative_caveats(normalized_answer, answer_plan, hit_by_id))
        issues.extend(self._check_follow_up_question_count(answer))

        deduped = self._dedupe(issues)
        return InventoryAnswerVerification(
            passed=not deduped,
            issues=deduped,
            checked_final_answer=True,
            final_answer_issues=deduped,
        )

    def verify_product_fit(
        self,
        *,
        answer_plan: InventoryAnswerPlan,
        hits: list[InventorySearchHit],
    ) -> InventoryAnswerVerification:
        preferences = answer_plan.preferences if isinstance(answer_plan.preferences, dict) else {}
        detail_intent = answer_plan.detected_intent == "product_detail" or "product_detail" in answer_plan.intent
        requested_type = normalize_inventory_text(
            str(preferences.get("product_type") or answer_plan.product_type or "")
        )
        requested_family = normalize_inventory_text(
            str(
                preferences.get("product_family")
                or answer_plan.product_family
                or self.ontology.product_family(requested_type)
                or ""
            )
        )
        requested_category = normalize_inventory_text(str(preferences.get("category") or ""))
        if detail_intent:
            requested_type = ""
            requested_family = ""
            requested_category = ""
        bundle_intent = "bundle" in answer_plan.intent or answer_plan.detected_intent == "cross_sell"
        if bundle_intent:
            requested_type = ""
            requested_family = ""
            requested_category = ""
        budget_min = self._coerce_float(preferences.get("budget_min"))
        budget_max = self._coerce_float(preferences.get("budget_max"))
        needs_in_stock = bool(preferences.get("needs_in_stock"))
        avoid_product_types = {
            normalize_inventory_text(str(value))
            for value in preferences.get("avoid_product_types", [])
            if isinstance(value, str) and normalize_inventory_text(value)
        }
        spec_requirements = () if bundle_intent else self._spec_requirements_from_plan(preferences.get("spec_requirements"))

        hit_by_id = {hit.product_id: hit for hit in hits}
        evidence_by_id = self._candidate_evidence_by_id(answer_plan.evidence_contract)
        issues: list[str] = []
        primary_issues: list[str] = []

        primary_issues.extend(
            self._selection_fit_issues(
                label="Primary recommendation",
                role="primary",
                product_id=answer_plan.primary_product_id,
                hit_by_id=hit_by_id,
                evidence_by_id=evidence_by_id,
                requested_type=requested_type,
                requested_family=requested_family,
                requested_category=requested_category,
                budget_min=budget_min,
                budget_max=budget_max,
                needs_in_stock=needs_in_stock,
                spec_requirements=spec_requirements,
                avoid_product_types=avoid_product_types,
            )
        )
        issues.extend(primary_issues)
        for product_id in answer_plan.alternative_product_ids:
            issues.extend(
                self._selection_fit_issues(
                    label="Alternative recommendation",
                    role="alternative",
                    product_id=product_id,
                    hit_by_id=hit_by_id,
                    evidence_by_id=evidence_by_id,
                    requested_type=requested_type,
                    requested_family=requested_family,
                    requested_category=requested_category,
                    budget_min=budget_min,
                    budget_max=budget_max,
                    needs_in_stock=needs_in_stock,
                    spec_requirements=spec_requirements,
                    avoid_product_types=avoid_product_types,
                )
            )

        deduped = self._dedupe(issues)
        deduped_primary = self._dedupe(primary_issues)
        return InventoryAnswerVerification(
            passed=not deduped,
            issues=deduped,
            hard_constraint_issues=deduped,
            requires_abstention=bool(deduped_primary),
        )

    def _check_excluded_products(
        self,
        normalized_answer: str,
        answer_plan: InventoryAnswerPlan,
        hit_by_id: dict[str, InventorySearchHit],
    ) -> list[str]:
        issues: list[str] = []
        for product_id in answer_plan.excluded_product_ids:
            hit = hit_by_id.get(product_id)
            if hit is None:
                continue
            if self._mentions_hit(normalized_answer, hit):
                issues.append(f"Final answer mentions excluded product {hit.name}.")
        return issues

    def _check_invented_product_names(self, answer: str, hits: list[InventorySearchHit]) -> list[str]:
        known_names = {normalize_inventory_text(hit.name) for hit in hits}
        known_skus = {normalize_inventory_text(hit.sku) for hit in hits}
        issues: list[str] = []
        product_nouns = set(self.ontology.PRODUCT_SYNONYMS)
        title_phrases = re.findall(r"\b(?:[A-Z][A-Za-z0-9]+(?:\s+|$)){2,5}", answer)
        for phrase in title_phrases:
            normalized_phrase = normalize_inventory_text(phrase)
            if not normalized_phrase:
                continue
            if normalized_phrase in known_names or normalized_phrase in known_skus:
                continue
            if any(normalized_phrase in name or name in normalized_phrase for name in known_names):
                continue
            if any(noun in normalized_phrase.split() for noun in product_nouns):
                issues.append(f"Final answer may contain unsupported product name: {phrase.strip()}.")
        return issues

    def _check_primary_product_grounding(
        self,
        normalized_answer: str,
        answer_plan: InventoryAnswerPlan,
        hit_by_id: dict[str, InventorySearchHit],
    ) -> list[str]:
        if answer_plan.abstain or not answer_plan.primary_product_id:
            return []
        if any(token in (answer_plan.intent or "") for token in ("small_talk", "no_match")):
            return []
        primary = hit_by_id.get(answer_plan.primary_product_id)
        if primary is None:
            return []
        if self._mentions_hit(normalized_answer, primary):
            return []

        mentions_secondary = any(
            self._mentions_hit(normalized_answer, hit_by_id[product_id])
            for product_id in [*answer_plan.alternative_product_ids, *answer_plan.cross_sell_product_ids]
            if product_id in hit_by_id
        )
        if mentions_secondary:
            return [f"Final answer mentions secondary options without naming the primary product {primary.name}."]

        should_name_primary = bool(
            answer_plan.alternative_product_ids
            or answer_plan.cross_sell_product_ids
            or any(
                token in (answer_plan.intent or "")
                for token in (
                    "sales",
                    "comparison",
                    "restock",
                    "product_detail",
                    "bundle",
                    "recommendation",
                )
            )
            or any(word in normalized_answer for word in self.RECOMMENDATION_WORDS)
        )
        if should_name_primary:
            return [f"Final answer does not name the grounded primary product {primary.name}."]
        return []

    def _check_prices(
        self,
        answer: str,
        hits: list[InventorySearchHit],
        contract: InventoryEvidenceContract | None,
    ) -> list[str]:
        mentioned_prices = self._extract_prices(answer)
        if not mentioned_prices:
            return []
        supported_prices = self._supported_prices(contract, hits)
        for first, second in combinations(sorted(supported_prices), 2):
            supported_prices.add(round(abs(first - second), 2))
        sorted_prices = sorted(supported_prices)
        for size in range(2, min(5, len(sorted_prices)) + 1):
            for price_group in combinations(sorted_prices, size):
                supported_prices.add(round(sum(price_group), 2))
        issues: list[str] = []
        for price in mentioned_prices:
            if not any(abs(price - supported) <= 0.01 for supported in supported_prices):
                issues.append(f"Final answer mentions unsupported price amount {price:.2f}.")
        return issues

    def _check_stock(
        self,
        answer: str,
        hits: list[InventorySearchHit],
        contract: InventoryEvidenceContract | None,
    ) -> list[str]:
        stock_mentions = [
            int(match.group(1))
            for match in re.finditer(
                r"\b(\d+)\s+(?:unit|units|in stock|left|available|on hand)",
                answer,
                flags=re.IGNORECASE,
            )
        ]
        stock_mentions.extend(
            int(match.group(1))
            for match in re.finditer(r"\bstock\s+(?:is\s+)?(\d+)\b", answer, flags=re.IGNORECASE)
        )
        if not stock_mentions:
            return []
        supported_stock = self._supported_stock(contract, hits)
        issues: list[str] = []
        for stock in stock_mentions:
            if stock not in supported_stock:
                issues.append(f"Final answer mentions unsupported stock quantity {stock}.")
        return issues

    def _check_unsupported_claims(
        self,
        normalized_answer: str,
        contract: InventoryEvidenceContract | None,
        hits: list[InventorySearchHit],
    ) -> list[str]:
        normalized_allowed_claims = (
            normalize_inventory_text(" ".join(contract.allowed_claims))
            if contract is not None and contract.allowed_claims
            else ""
        )
        evidence_text = normalize_inventory_text(
            " ".join(
                " ".join(
                    [
                        hit.name,
                        hit.sku,
                        hit.category or "",
                        hit.brand or "",
                        hit.status or "",
                        hit.snippet or "",
                        " ".join(hit.tags),
                        " ".join(f"{key} {value}" for key, value in sorted(hit.attributes.items())),
                        str(hit.metadata),
                    ]
                )
                for hit in hits
            )
        )
        issues: list[str] = []
        for claim in self.SUSPICIOUS_UNSUPPORTED_CLAIMS:
            allowed = claim in normalized_allowed_claims if normalized_allowed_claims else False
            supported_by_hits = claim in evidence_text
            if claim in normalized_answer and not allowed and not supported_by_hits:
                issues.append(f"Final answer contains unsupported claim: {claim}.")
        return issues

    def _check_abstention(self, normalized_answer: str, answer_plan: InventoryAnswerPlan) -> list[str]:
        if not answer_plan.abstain:
            return []
        if any(word in normalized_answer for word in self.NO_MATCH_WORDS):
            return []
        if any(word in normalized_answer for word in self.RECOMMENDATION_WORDS):
            return ["Final answer does not respect abstention state."]
        return []

    def _check_cross_sell_boundary(
        self,
        normalized_answer: str,
        answer_plan: InventoryAnswerPlan,
        hit_by_id: dict[str, InventorySearchHit],
    ) -> list[str]:
        issues: list[str] = []
        for product_id in answer_plan.cross_sell_product_ids:
            hit = hit_by_id.get(product_id)
            if hit is None or not self._mentions_hit(normalized_answer, hit):
                continue
            window = self._mention_window(normalized_answer, normalize_inventory_text(hit.name))
            if "not a substitute" in window or "not a replacement" in window:
                continue
            if any(word in window for word in self.SUBSTITUTE_WORDS):
                issues.append(f"Final answer may treat cross-sell {hit.name} as a substitute.")
        return issues

    def _check_near_alternative_caveats(
        self,
        normalized_answer: str,
        answer_plan: InventoryAnswerPlan,
        hit_by_id: dict[str, InventorySearchHit],
    ) -> list[str]:
        primary = hit_by_id.get(answer_plan.primary_product_id or "")
        if primary is None:
            return []
        primary_type = self.ontology.detect_product_type(product=primary)
        issues: list[str] = []
        for product_id in answer_plan.alternative_product_ids:
            alternative = hit_by_id.get(product_id)
            if alternative is None or not self._mentions_hit(normalized_answer, alternative):
                continue
            alternative_type = self.ontology.detect_product_type(product=alternative)
            if not primary_type or not alternative_type or primary_type == alternative_type:
                continue
            window = self._mention_window(normalized_answer, normalize_inventory_text(alternative.name))
            if not any(word in window for word in self.CAVEAT_WORDS):
                issues.append(
                    f"Final answer mentions near alternative {alternative.name} without a substitute caveat."
                )
        return issues

    @staticmethod
    def _extract_prices(answer: str) -> list[float]:
        prices: list[float] = []
        patterns = [
            r"\bUSD\s*(\d+(?:\.\d{1,2})?)\b",
            r"\$\s*(\d+(?:\.\d{1,2})?)\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, answer, flags=re.IGNORECASE):
                prices.append(round(float(match.group(1)), 2))
        return prices

    @staticmethod
    def _mentions_hit(normalized_answer: str, hit: InventorySearchHit) -> bool:
        normalized_name = normalize_inventory_text(hit.name)
        normalized_sku = normalize_inventory_text(hit.sku)
        return bool(
            (normalized_name and normalized_name in normalized_answer)
            or (normalized_sku and normalized_sku in normalized_answer)
        )

    @staticmethod
    def _mention_window(normalized_answer: str, phrase: str, radius: int = 96) -> str:
        if not phrase:
            return normalized_answer[:radius]
        index = normalized_answer.find(phrase)
        if index < 0:
            return normalized_answer
        return normalized_answer[max(0, index - radius): index + len(phrase) + radius]

    @staticmethod
    def _dedupe(issues: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for issue in issues:
            if issue in seen:
                continue
            seen.add(issue)
            deduped.append(issue)
        return deduped

    def _supported_prices(
        self,
        contract: InventoryEvidenceContract | None,
        hits: list[InventorySearchHit],
    ) -> set[float]:
        supported = {round(hit.price, 2) for hit in hits if hit.price is not None}
        if contract is None:
            return supported
        for candidate in contract.candidate_evidence:
            for fact in candidate.facts:
                if fact.key == "price" and fact.status == "present" and isinstance(fact.value, (int, float)):
                    supported.add(round(float(fact.value), 2))
        return supported

    def _supported_stock(
        self,
        contract: InventoryEvidenceContract | None,
        hits: list[InventorySearchHit],
    ) -> set[int]:
        supported = {hit.stock for hit in hits if hit.stock is not None}
        if contract is None:
            return supported
        for candidate in contract.candidate_evidence:
            for fact in candidate.facts:
                if fact.key != "stock":
                    continue
                if fact.status == "present" and isinstance(fact.value, int):
                    supported.add(int(fact.value))
                if fact.status == "conflicting" and isinstance(fact.value, dict):
                    for value in fact.value.values():
                        if isinstance(value, int):
                            supported.add(value)
        return supported

    def _selection_fit_issues(
        self,
        *,
        label: str,
        role: str,
        product_id: str | None,
        hit_by_id: dict[str, InventorySearchHit],
        evidence_by_id: dict[str, InventoryProductEvidence],
        requested_type: str,
        requested_family: str,
        requested_category: str,
        budget_min: float | None,
        budget_max: float | None,
        needs_in_stock: bool,
        spec_requirements: tuple[InventorySpecRequirement, ...],
        avoid_product_types: set[str],
    ) -> list[str]:
        if not product_id:
            return []
        hit = hit_by_id.get(product_id)
        if hit is None:
            return []
        evidence = evidence_by_id.get(product_id)
        issues: list[str] = []

        product_type = normalize_inventory_text(self.ontology.detect_product_type(product=hit) or "")
        product_family = normalize_inventory_text(self.ontology.product_family(product_type) or "")
        product_category = normalize_inventory_text(hit.category)

        if requested_category and product_category != requested_category:
            issues.append(
                f"{label} {hit.name} is in category {hit.category or 'unknown'}, not the required {requested_category} category."
            )
        if product_type and product_type in avoid_product_types:
            issues.append(f"{label} {hit.name} is a blocked product type: {product_type}.")
        if role == "primary" and requested_type:
            if not product_type:
                issues.append(f"{label} {hit.name} cannot be verified as the requested {requested_type} type.")
            elif product_type != requested_type:
                issues.append(f"{label} {hit.name} is {product_type}, not the requested {requested_type}.")
        if role == "alternative":
            if requested_family:
                if not product_family:
                    issues.append(
                        f"{label} {hit.name} cannot be verified as part of the required {requested_family} product family."
                    )
                elif product_family != requested_family:
                    issues.append(
                        f"{label} {hit.name} is outside the required {requested_family} product family."
                    )
            elif requested_type:
                if not product_type:
                    issues.append(f"{label} {hit.name} cannot be verified as the requested {requested_type} type.")
                elif product_type != requested_type:
                    issues.append(f"{label} {hit.name} is {product_type}, not the requested {requested_type}.")

        price = self._resolved_price(hit=hit, evidence=evidence)
        if budget_min is not None:
            if price is None:
                issues.append(
                    f"{label} {hit.name} has no verified price, so the minimum budget {budget_min:.2f} cannot be checked."
                )
            elif price < budget_min - 0.01:
                issues.append(
                    f"{label} {hit.name} is priced at {price:.2f}, below the required minimum budget {budget_min:.2f}."
                )
        if budget_max is not None:
            if price is None:
                issues.append(
                    f"{label} {hit.name} has no verified price, so the budget ceiling {budget_max:.2f} cannot be checked."
                )
            elif price > budget_max + 0.01:
                issues.append(
                    f"{label} {hit.name} is priced at {price:.2f}, above the budget ceiling {budget_max:.2f}."
                )

        if needs_in_stock:
            stock_status, stock_value = self._resolved_stock(hit=hit, evidence=evidence)
            if stock_status == "conflicting":
                issues.append(f"{label} {hit.name} has conflicting stock evidence, so in-stock fit is not reliable.")
            elif stock_value is None:
                issues.append(f"{label} {hit.name} has no verified stock value, so in-stock fit cannot be checked.")
            elif stock_value <= 0:
                issues.append(f"{label} {hit.name} is not currently in stock.")

        for requirement in spec_requirements:
            actual = self._resolved_spec_value(hit=hit, evidence=evidence, key=requirement.key)
            if actual is None:
                issues.append(f"{label} {hit.name} is missing the required spec {requirement.key}.")
                continue
            if not self._spec_requirement_satisfied(actual, requirement):
                issues.append(
                    f"{label} {hit.name} fails the required spec {requirement.key} {requirement.operator} {requirement.value}."
                )

        return issues

    @staticmethod
    def _check_follow_up_question_count(answer: str) -> list[str]:
        question_count = answer.count("?")
        if question_count <= 1:
            return []
        return [f"Final answer asks {question_count} follow-up questions, which exceeds the one-question limit."]

    @staticmethod
    def _candidate_evidence_by_id(
        contract: InventoryEvidenceContract | None,
    ) -> dict[str, InventoryProductEvidence]:
        if contract is None:
            return {}
        return {candidate.product_id: candidate for candidate in contract.candidate_evidence}

    @staticmethod
    def _coerce_float(value: object | None) -> float | None:
        return coerce_spec_number(value)

    @staticmethod
    def _spec_requirements_from_plan(payload: object | None) -> tuple[InventorySpecRequirement, ...]:
        if not isinstance(payload, list):
            return ()
        requirements: list[InventorySpecRequirement] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            operator = str(item.get("operator") or "").strip()
            value = item.get("value")
            if not key or operator not in {"eq", "gte"}:
                continue
            requirements.append(InventorySpecRequirement(key=key, operator=operator, value=value))
        return tuple(requirements)

    @staticmethod
    def _fact_value(
        evidence: InventoryProductEvidence | None,
        key: str,
    ) -> tuple[str | None, object | None]:
        if evidence is None:
            return None, None
        for fact in evidence.facts:
            if fact.key == key:
                return fact.status, fact.value
        return None, None

    def _resolved_price(
        self,
        *,
        hit: InventorySearchHit,
        evidence: InventoryProductEvidence | None,
    ) -> float | None:
        fact_status, fact_value = self._fact_value(evidence, "price")
        if fact_status == "present" and isinstance(fact_value, (int, float)):
            return float(fact_value)
        return float(hit.price) if hit.price is not None else None

    def _resolved_stock(
        self,
        *,
        hit: InventorySearchHit,
        evidence: InventoryProductEvidence | None,
    ) -> tuple[str, int | None]:
        fact_status, fact_value = self._fact_value(evidence, "stock")
        if fact_status == "conflicting":
            return "conflicting", None
        if fact_status == "present" and isinstance(fact_value, int):
            return "present", int(fact_value)
        if fact_status == "missing":
            return "missing", None
        return ("present", hit.stock) if hit.stock is not None else ("missing", None)

    def _resolved_spec_value(
        self,
        *,
        hit: InventorySearchHit,
        evidence: InventoryProductEvidence | None,
        key: str,
    ) -> object | None:
        fact_status, fact_value = self._fact_value(evidence, f"spec.{key.casefold()}")
        if fact_status == "present":
            return fact_value
        return self._hit_metadata_value(hit, key)

    def _hit_metadata_value(self, hit: InventorySearchHit, key: str) -> object | None:
        aliases = self.SPEC_METADATA_ALIASES.get(key, (key,))
        for alias in aliases:
            if alias in hit.metadata:
                return hit.metadata.get(alias)
        raw_attributes = hit.metadata.get("raw_attributes")
        if isinstance(raw_attributes, dict):
            for alias in aliases:
                if alias in raw_attributes:
                    return raw_attributes.get(alias)
        for alias in aliases:
            if alias in hit.attributes:
                return hit.attributes.get(alias)
        return None

    def _spec_requirement_satisfied(
        self,
        actual: object | None,
        requirement: InventorySpecRequirement,
    ) -> bool:
        if actual is None:
            return False
        if requirement.operator == "eq":
            return spec_requirement_satisfied(
                actual,
                key=requirement.key,
                operator=requirement.operator,
                expected=requirement.value,
            )
        return spec_requirement_satisfied(
            actual,
            key=requirement.key,
            operator=requirement.operator,
            expected=requirement.value,
        )

    def _coerce_bool(self, value: object | None) -> bool | None:
        return coerce_spec_bool(value)
