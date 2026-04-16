from __future__ import annotations

import re
from itertools import combinations

from app.core.schemas import InventoryAnswerPlan, InventoryAnswerVerification, InventorySearchHit
from app.inventory.ontology import ProductOntology, normalize_inventory_text


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
        issues: list[str] = []

        issues.extend(self._check_excluded_products(normalized_answer, answer_plan, hit_by_id))
        issues.extend(self._check_invented_product_names(answer, hits))
        issues.extend(self._check_prices(answer, hits))
        issues.extend(self._check_stock(answer, hits))
        issues.extend(self._check_unsupported_claims(normalized_answer, hits))
        issues.extend(self._check_abstention(normalized_answer, answer_plan))
        issues.extend(self._check_cross_sell_boundary(normalized_answer, answer_plan, hit_by_id))
        issues.extend(self._check_near_alternative_caveats(normalized_answer, answer_plan, hit_by_id))

        deduped = self._dedupe(issues)
        return InventoryAnswerVerification(
            passed=not deduped,
            issues=deduped,
            checked_final_answer=True,
            final_answer_issues=deduped,
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

    def _check_prices(self, answer: str, hits: list[InventorySearchHit]) -> list[str]:
        mentioned_prices = self._extract_prices(answer)
        if not mentioned_prices:
            return []
        supported_prices = {round(hit.price, 2) for hit in hits if hit.price is not None}
        for first, second in combinations(sorted(supported_prices), 2):
            supported_prices.add(round(abs(first - second), 2))
        issues: list[str] = []
        for price in mentioned_prices:
            if not any(abs(price - supported) <= 0.01 for supported in supported_prices):
                issues.append(f"Final answer mentions unsupported price amount {price:.2f}.")
        return issues

    def _check_stock(self, answer: str, hits: list[InventorySearchHit]) -> list[str]:
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
        supported_stock = {hit.stock for hit in hits if hit.stock is not None}
        issues: list[str] = []
        for stock in stock_mentions:
            if stock not in supported_stock:
                issues.append(f"Final answer mentions unsupported stock quantity {stock}.")
        return issues

    def _check_unsupported_claims(self, normalized_answer: str, hits: list[InventorySearchHit]) -> list[str]:
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
            if claim in normalized_answer and claim not in evidence_text:
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
    def _mention_window(normalized_answer: str, normalized_name: str, *, radius: int = 90) -> str:
        index = normalized_answer.find(normalized_name)
        if index < 0:
            return ""
        return normalized_answer[max(0, index - radius): index + len(normalized_name) + radius]

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
