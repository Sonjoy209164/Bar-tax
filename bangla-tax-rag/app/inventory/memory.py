from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.schemas import InventoryAnswerPlan, InventoryMemoryResolution, InventorySearchFilters
from app.inventory.ontology import ProductOntology, normalize_inventory_text


@dataclass(frozen=True)
class InventoryResolvedMemory:
    filters: InventorySearchFilters
    resolution: InventoryMemoryResolution


class InventoryMemoryResolver:
    """Safely resolves follow-up references without letting old memory override new intent."""

    REFERENCE_TERMS = (
        "it",
        "this",
        "that",
        "eta",
        "etar",
        "eita",
        "eitar",
        "ota",
        "otar",
        "oita",
        "seta",
        "shetar",
        "tar",
        "er dam",
        "price",
        "dam",
        "size",
        "stock",
        "that one",
        "this one",
        "same one",
        "the first one",
        "first one",
        "the second one",
        "second one",
        "the third one",
        "third one",
        "the cheaper one",
        "cheaper one",
        "fallback",
        "alternative",
        "that product",
        "this product",
        "eta product",
        "oi product",
        "compare it",
        "compare that",
        "tell me more",
        "more about it",
        "more about that",
        "same design",
        "same design e",
        "same design er",
        "ei design",
        "same color",
        "same colour",
        "another color",
        "other color",
        "onno color",
        "ar ki color",
        "aro color",
        "white",
        "black",
        "blue",
        "red",
        "green",
        "grey",
        "gray",
        "brown",
        "available",
        "show similar",
        "similar",
        "cheaper",
        "matching",
        "sathe matching",
        "go with",
        "what goes with",
        "এটা",
        "এটি",
        "এটির",
        "এটার",
        "ওটা",
        "ওটার",
        "সেটা",
        "সেটার",
        "তার",
        "এর দাম",
        "দাম",
        "কত",
        "সাইজ",
        "স্টক",
        "দ্বিতীয়",
        "দ্বিতীয়টার",
        "তৃতীয়",
        "তৃতীয়টার",
        "আর কালার",
        "একই ডিজাইন",
        "এই ডিজাইন",
        "অর্ডার",
    )
    NEW_REQUEST_TERMS = (
        "show me",
        "find",
        "find me",
        "list",
        "search",
        "recommend",
        "suggest",
        "do you have",
        "have any",
        "ache",
        "ase",
        "dekhao",
        "dekhaw",
        "dekhate",
        "lagbe",
        "chai",
        "চাই",
        "লাগবে",
        "দেখাও",
        "আছে",
    )
    ALTERNATIVE_TERMS = ("cheaper", "fallback", "alternative", "lower price", "less expensive", "kom dam", "similar", "aro")
    CROSS_SELL_TERMS = ("add on", "add-on", "accessory", "bundle", "go with", "pair with", "cross sell", "cross-sell", "matching", "manabe")
    FIRST_TERMS = ("first", "top", "primary", "prothom", "প্রথম")
    SECOND_TERMS = ("second", "next", "ditiyo", "dwitiyo", "দ্বিতীয়")
    THIRD_TERMS = ("third", "tritiyo", "তৃতীয়")

    def __init__(self, ontology: ProductOntology | None = None) -> None:
        self.ontology = ontology or ProductOntology()

    def resolve(
        self,
        *,
        question: str,
        filters: InventorySearchFilters,
        focused_product_ids: list[str],
        active_filters: InventorySearchFilters | None,
        last_answer_plan: InventoryAnswerPlan | None,
    ) -> InventoryResolvedMemory:
        normalized_question = self._memory_text(question)
        explicit_request = self._has_explicit_new_request(normalized_question, filters)
        has_memory = bool(focused_product_ids or active_filters or last_answer_plan)
        if not has_memory:
            return InventoryResolvedMemory(filters=filters, resolution=InventoryMemoryResolution())

        if filters.product_ids:
            return InventoryResolvedMemory(
                filters=filters,
                resolution=InventoryMemoryResolution(
                    ignored_memory_reason="Current request already includes explicit product_ids.",
                    memory_policy_reason="explicit product filter beats conversation memory",
                ),
            )

        if (
            self.ontology.detect_product_type(text=normalized_question)
            and not self._has_direct_anchor_reference(normalized_question)
        ):
            return InventoryResolvedMemory(
                filters=filters,
                resolution=InventoryMemoryResolution(
                    ignored_memory_reason="Current question contains a fresh product/category mention.",
                    memory_policy_reason="new product/category mention blocks old product focus",
                ),
            )

        if explicit_request and not self._has_reference(normalized_question):
            return InventoryResolvedMemory(
                filters=filters,
                resolution=InventoryMemoryResolution(
                    ignored_memory_reason="Current question contains a new explicit product/category request.",
                    memory_policy_reason="new explicit request blocks old product focus",
                ),
            )

        should_use_context_filters = self._should_use_context_filters(
            normalized_question=normalized_question,
            filters=filters,
            active_filters=active_filters,
        )
        should_use_reference = self._has_reference(normalized_question)

        resolved_filters = filters.model_copy(deep=True)
        applied_context_filters = False
        if should_use_context_filters and active_filters is not None:
            resolved_filters = self._merge_context_filters(base=active_filters, override=filters)
            applied_context_filters = resolved_filters != filters

        resolved_product_ids = self._resolve_product_ids(
            normalized_question=normalized_question,
            focused_product_ids=focused_product_ids,
            last_answer_plan=last_answer_plan,
        ) if should_use_reference else []
        if resolved_product_ids:
            resolved_filters.product_ids = resolved_product_ids

        used_memory = bool(resolved_product_ids or applied_context_filters)
        reason = None
        if resolved_product_ids:
            reason = "Resolved follow-up reference to prior focused product IDs."
        elif applied_context_filters:
            reason = "Applied active context filters to a follow-up request."

        return InventoryResolvedMemory(
            filters=resolved_filters,
            resolution=InventoryMemoryResolution(
                used_memory=used_memory,
                reason=reason,
                resolved_product_ids=resolved_product_ids,
                applied_context_filters=applied_context_filters,
                ignored_memory_reason=None if used_memory else "Memory was provided but no safe reference was detected.",
                memory_source=(
                    "focused_product_ids"
                    if resolved_product_ids
                    else "active_filters"
                    if applied_context_filters
                    else None
                ),
                memory_confidence=1.0 if used_memory else None,
                memory_policy_reason=(
                    "clear reference resolved against focused product context"
                    if resolved_product_ids
                    else "active context filters applied to a follow-up"
                    if applied_context_filters
                    else "no clear follow-up reference detected"
                ),
            ),
        )

    def _resolve_product_ids(
        self,
        *,
        normalized_question: str,
        focused_product_ids: list[str],
        last_answer_plan: InventoryAnswerPlan | None,
    ) -> list[str]:
        if self._has_any(normalized_question, self.CROSS_SELL_TERMS):
            cross_sell = list((last_answer_plan.cross_sell_product_ids if last_answer_plan else []) or [])
            if cross_sell:
                return self._dedupe(cross_sell)
            primary = [last_answer_plan.primary_product_id] if last_answer_plan and last_answer_plan.primary_product_id else []
            return self._dedupe(primary or focused_product_ids[:1])
        if self._has_any(normalized_question, self.ALTERNATIVE_TERMS):
            candidates = list((last_answer_plan.alternative_product_ids if last_answer_plan else []) or [])
            if candidates:
                return self._dedupe(candidates[:2])
            return self._dedupe(focused_product_ids[1:2])
        if self._has_any(normalized_question, self.SECOND_TERMS):
            candidates = list((last_answer_plan.alternative_product_ids if last_answer_plan else []) or [])
            if candidates:
                return self._dedupe(candidates[:1])
            return self._dedupe(focused_product_ids[1:2])
        if self._has_any(normalized_question, self.THIRD_TERMS):
            return self._dedupe(focused_product_ids[2:3])
        if self._has_any(normalized_question, self.FIRST_TERMS):
            primary = [last_answer_plan.primary_product_id] if last_answer_plan and last_answer_plan.primary_product_id else []
            return self._dedupe(primary or focused_product_ids[:1])
        primary = [last_answer_plan.primary_product_id] if last_answer_plan and last_answer_plan.primary_product_id else []
        return self._dedupe(focused_product_ids[:1] or primary)

    def _should_use_context_filters(
        self,
        *,
        normalized_question: str,
        filters: InventorySearchFilters,
        active_filters: InventorySearchFilters | None,
    ) -> bool:
        if active_filters is None or self._has_structured_filters(filters):
            return False
        if self._has_reference(normalized_question):
            return True
        return self._has_any(
            normalized_question,
            (
                "cheaper",
                "lower price",
                "more expensive",
                "premium",
                "budget",
                "more options",
                "other options",
                "available",
                "in stock",
            ),
        )

    def _has_explicit_new_request(self, normalized_question: str, filters: InventorySearchFilters) -> bool:
        if any((filters.categories, filters.brands, filters.tags)):
            return True
        detected_product_type = self.ontology.detect_product_type(text=normalized_question)
        return bool(detected_product_type and self._has_any(normalized_question, self.NEW_REQUEST_TERMS))

    def _has_reference(self, normalized_question: str) -> bool:
        if self._has_any(normalized_question, self.REFERENCE_TERMS):
            return True
        if self._has_any(normalized_question, self.CROSS_SELL_TERMS):
            return True
        if self._has_any(normalized_question, self.ALTERNATIVE_TERMS):
            return True
        return bool(re.search(r"\b(the\s+)?(?:first|second|third)\s+(?:one|product|item|option)\b", normalized_question))

    def _has_direct_anchor_reference(self, normalized_question: str) -> bool:
        return self._has_any(
            normalized_question,
            (
                "eta",
                "eita",
                "etar",
                "eitar",
                "ei ta",
                "this",
                "this one",
                "that",
                "that one",
                "it",
                "এটা",
                "এটার",
                "এটি",
                "এটির",
                "এইটা",
                "এইটার",
                "ওটা",
                "ওটার",
                "সেটা",
                "সেটার",
            ),
        )

    @staticmethod
    def _merge_context_filters(
        *,
        base: InventorySearchFilters,
        override: InventorySearchFilters,
    ) -> InventorySearchFilters:
        merged = base.model_copy(deep=True)
        if override.product_ids:
            merged.product_ids = list(override.product_ids)
        if override.categories:
            merged.categories = list(override.categories)
        if override.brands:
            merged.brands = list(override.brands)
        if override.statuses:
            merged.statuses = list(override.statuses)
        if override.tags:
            merged.tags = list(override.tags)
        for field_name in ("min_stock", "max_stock", "min_price", "max_price"):
            override_value = getattr(override, field_name)
            if override_value is not None:
                setattr(merged, field_name, override_value)
        merged.rag_only = override.rag_only
        return merged

    @staticmethod
    def _has_structured_filters(filters: InventorySearchFilters) -> bool:
        return any(
            (
                filters.product_ids,
                filters.categories,
                filters.brands,
                filters.statuses,
                filters.tags,
                filters.min_stock is not None,
                filters.max_stock is not None,
                filters.min_price is not None,
                filters.max_price is not None,
            )
        )

    @staticmethod
    def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
        return any(InventoryMemoryResolver._has_phrase(text, phrase) for phrase in phrases)

    @staticmethod
    def _has_phrase(text: str, phrase: str) -> bool:
        normalized_phrase = normalize_inventory_text(phrase)
        if not normalized_phrase:
            if InventoryMemoryResolver._has_bangla(phrase):
                return phrase in text
            return False
        pattern = re.escape(normalized_phrase).replace(r"\ ", r"\s+")
        return bool(re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text))

    @staticmethod
    def _memory_text(text: str) -> str:
        normalized = normalize_inventory_text(text)
        raw = text.casefold()
        return f"{normalized} {raw}".strip()

    @staticmethod
    def _has_bangla(text: str) -> bool:
        return any("\u0980" <= char <= "\u09ff" for char in text)

    @staticmethod
    def _dedupe(product_ids: list[str | None]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for product_id in product_ids:
            if not product_id or product_id in seen:
                continue
            seen.add(product_id)
            deduped.append(product_id)
        return deduped
