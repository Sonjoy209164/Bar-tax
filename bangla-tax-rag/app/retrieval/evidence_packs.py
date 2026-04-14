from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.core.utils import extract_definition_target
from app.domain import CitationRelation, EvidenceItem, LegalCitation, QueryType
from app.retrieval.hybrid_retriever import HybridCandidate, HybridRetrievalResult


class EvidencePackType(StrEnum):
    GENERAL = "general"
    DEFINITION = "definition"
    SECTION_LOOKUP = "section_lookup"
    RATE_TABLE = "rate_table"
    SCENARIO = "scenario"
    CROSS_SECTION = "cross_section"
    COMPARISON = "comparison"


class EvidencePackBuilderConfig(BaseModel):
    max_primary_items: int = Field(default=3, ge=1, le=10)
    max_contextual_items: int = Field(default=4, ge=0, le=12)
    max_supporting_items: int = Field(default=5, ge=0, le=20)
    max_section_groups: int = Field(default=3, ge=1, le=8)


class SectionEvidenceGroup(BaseModel):
    label: str
    section_number: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class EvidencePack(BaseModel):
    pack_type: EvidencePackType
    question: str
    query_type: QueryType
    candidate_chunk_ids: list[str] = Field(default_factory=list)
    primary_evidence: list[EvidenceItem] = Field(default_factory=list)
    contextual_evidence: list[EvidenceItem] = Field(default_factory=list)
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_coverage: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_evidence(self) -> list[EvidenceItem]:
        return _dedupe_evidence(
            [
                *self.primary_evidence,
                *self.contextual_evidence,
                *self.supporting_evidence,
            ]
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def citations(self) -> list[LegalCitation]:
        citations: list[LegalCitation] = []
        seen: set[tuple[str, CitationRelation, str | None, str | None, str | None]] = set()
        for item in self.all_evidence:
            key = (
                item.citation.node_id,
                item.citation.relation,
                item.citation.section_number,
                item.citation.subsection_number,
                item.citation.clause_number,
            )
            if key in seen:
                continue
            citations.append(item.citation)
            seen.add(key)
        return citations

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dominant_section_numbers(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for item in self.all_evidence:
            if not item.citation.section_number or item.citation.section_number in seen:
                continue
            seen.add(item.citation.section_number)
            ordered.append(item.citation.section_number)
        return ordered


class DefinitionEvidencePack(EvidencePack):
    definition_term: str | None = None
    definition_evidence: list[EvidenceItem] = Field(default_factory=list)
    governing_evidence: list[EvidenceItem] = Field(default_factory=list)


class SectionLookupEvidencePack(EvidencePack):
    target_section_number: str | None = None
    anchor_evidence: list[EvidenceItem] = Field(default_factory=list)
    section_context_evidence: list[EvidenceItem] = Field(default_factory=list)


class RateTableEvidencePack(EvidencePack):
    target_section_number: str | None = None
    table_evidence: list[EvidenceItem] = Field(default_factory=list)
    governing_rule_evidence: list[EvidenceItem] = Field(default_factory=list)


class ScenarioEvidencePack(EvidencePack):
    rule_evidence: list[EvidenceItem] = Field(default_factory=list)
    exception_evidence: list[EvidenceItem] = Field(default_factory=list)
    table_evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_facts_to_resolve: list[str] = Field(default_factory=list)


class CrossSectionEvidencePack(EvidencePack):
    section_groups: list[SectionEvidenceGroup] = Field(default_factory=list)


class ComparisonEvidencePack(EvidencePack):
    comparison_groups: list[SectionEvidenceGroup] = Field(default_factory=list)


@dataclass(frozen=True)
class _RankedEvidence:
    item: EvidenceItem
    candidate_index: int
    candidate: HybridCandidate | None


class EvidencePackBuilder:
    def __init__(self, config: EvidencePackBuilderConfig | None = None) -> None:
        self.config = config or EvidencePackBuilderConfig()

    def build(self, result: HybridRetrievalResult) -> EvidencePack:
        query_type = result.query_plan.query_type
        if query_type is QueryType.DEFINITION:
            return self._build_definition_pack(result)
        if query_type is QueryType.SECTION_LOOKUP:
            return self._build_section_lookup_pack(result)
        if query_type in {QueryType.TABLE_LOOKUP, QueryType.RATE_LOOKUP, QueryType.AMOUNT_LOOKUP}:
            return self._build_rate_table_pack(result)
        if query_type in {QueryType.SCENARIO_REASONING, QueryType.ELIGIBILITY}:
            return self._build_scenario_pack(result)
        if query_type is QueryType.CROSS_SECTION_REASONING:
            return self._build_cross_section_pack(result)
        if query_type is QueryType.COMPARISON:
            return self._build_comparison_pack(result)
        return self._build_general_pack(result)

    def _build_definition_pack(self, result: HybridRetrievalResult) -> DefinitionEvidencePack:
        ranked = _collect_ranked_evidence(result)
        direct = [entry.item for entry in ranked if entry.item.citation.relation is CitationRelation.DIRECT]
        definition_evidence = _take(
            [
                item
                for item in direct
                if _node_type(item) in {"definition", "clause", "subsection", "section"}
            ]
            or direct,
            self.config.max_primary_items,
        )
        governing = _take(
            [
                entry.item
                for entry in ranked
                if entry.item.citation.relation in {CitationRelation.PARENT_CONTEXT, CitationRelation.GOVERNING_RULE}
            ],
            self.config.max_contextual_items,
        )
        supporting = _take(
            [
                entry.item
                for entry in ranked
                if entry.item not in definition_evidence and entry.item not in governing
            ],
            self.config.max_supporting_items,
        )
        missing_coverage = _base_missing_coverage(governing)
        if not definition_evidence:
            missing_coverage.append("No direct definitional evidence was selected.")
        notes = ["Selected direct definition evidence and linked governing context."]
        return DefinitionEvidencePack(
            pack_type=EvidencePackType.DEFINITION,
            question=result.question,
            query_type=result.query_plan.query_type,
            candidate_chunk_ids=[candidate.chunk.chunk_id for candidate in result.candidates],
            primary_evidence=definition_evidence,
            contextual_evidence=governing,
            supporting_evidence=supporting,
            missing_coverage=missing_coverage,
            notes=notes,
            metadata={"query_notes": result.query_plan.notes},
            definition_term=(extract_definition_target(result.query_plan.normalized_question) or "").lower() or None,
            definition_evidence=definition_evidence,
            governing_evidence=governing,
        )

    def _build_section_lookup_pack(self, result: HybridRetrievalResult) -> SectionLookupEvidencePack:
        ranked = _collect_ranked_evidence(result)
        target_section = result.query_plan.section_references[0] if result.query_plan.section_references else None
        anchor_evidence = _take(
            [
                entry.item
                for entry in ranked
                if entry.item.citation.relation is CitationRelation.DIRECT
                and (not target_section or entry.item.citation.section_number == target_section)
                and entry.candidate is not None
                and entry.candidate.chunk.chunk_variant == "anchor"
            ]
            or [
                entry.item
                for entry in ranked
                if entry.item.citation.relation is CitationRelation.DIRECT
                and (not target_section or entry.item.citation.section_number == target_section)
            ],
            self.config.max_primary_items,
        )
        section_context = _take(
            [
                entry.item
                for entry in ranked
                if entry.item.citation.relation in {CitationRelation.PARENT_CONTEXT, CitationRelation.GOVERNING_RULE}
                and (not target_section or entry.item.citation.section_number == target_section)
            ],
            self.config.max_contextual_items,
        )
        supporting = _take(
            [
                entry.item
                for entry in ranked
                if entry.item not in anchor_evidence and entry.item not in section_context
            ],
            self.config.max_supporting_items,
        )
        missing_coverage = _base_missing_coverage(section_context)
        if target_section and not anchor_evidence:
            missing_coverage.append(f"No anchor evidence was selected for section {target_section}.")
        return SectionLookupEvidencePack(
            pack_type=EvidencePackType.SECTION_LOOKUP,
            question=result.question,
            query_type=result.query_plan.query_type,
            candidate_chunk_ids=[candidate.chunk.chunk_id for candidate in result.candidates],
            primary_evidence=anchor_evidence,
            contextual_evidence=section_context,
            supporting_evidence=supporting,
            missing_coverage=missing_coverage,
            notes=["Selected section anchor evidence plus linked section context."],
            metadata={"query_notes": result.query_plan.notes},
            target_section_number=target_section or _first_section_number(anchor_evidence),
            anchor_evidence=anchor_evidence,
            section_context_evidence=section_context,
        )

    def _build_rate_table_pack(self, result: HybridRetrievalResult) -> RateTableEvidencePack:
        ranked = _collect_ranked_evidence(result)
        target_section = result.query_plan.section_references[0] if result.query_plan.section_references else None
        table_evidence = _take(
            [
                entry.item
                for entry in ranked
                if _is_table_like(entry)
                and (not target_section or entry.item.citation.section_number == target_section)
            ],
            self.config.max_primary_items,
        )
        governing = _take(
            [
                entry.item
                for entry in ranked
                if entry.item.citation.relation in {CitationRelation.PARENT_CONTEXT, CitationRelation.GOVERNING_RULE}
            ],
            self.config.max_contextual_items,
        )
        primary = table_evidence or _take(
            [entry.item for entry in ranked if entry.item.citation.relation is CitationRelation.DIRECT],
            self.config.max_primary_items,
        )
        supporting = _take(
            [
                entry.item
                for entry in ranked
                if entry.item not in primary and entry.item not in governing
            ],
            self.config.max_supporting_items,
        )
        missing_coverage = _base_missing_coverage(governing)
        if not table_evidence:
            missing_coverage.append("No attached table or table-row evidence was selected.")
        return RateTableEvidencePack(
            pack_type=EvidencePackType.RATE_TABLE,
            question=result.question,
            query_type=result.query_plan.query_type,
            candidate_chunk_ids=[candidate.chunk.chunk_id for candidate in result.candidates],
            primary_evidence=primary,
            contextual_evidence=governing,
            supporting_evidence=supporting,
            missing_coverage=missing_coverage,
            notes=["Selected table/rate evidence and the linked governing rule context."],
            metadata={"query_notes": result.query_plan.notes},
            target_section_number=target_section or _first_section_number(primary),
            table_evidence=table_evidence,
            governing_rule_evidence=governing,
        )

    def _build_scenario_pack(self, result: HybridRetrievalResult) -> ScenarioEvidencePack:
        ranked = _collect_ranked_evidence(result)
        exception_evidence = _take(
            [
                entry.item
                for entry in ranked
                if _node_type(entry.item) in {"proviso", "explanation"}
            ],
            self.config.max_contextual_items,
        )
        table_evidence = _take(
            [entry.item for entry in ranked if _is_table_like(entry)],
            self.config.max_contextual_items,
        )
        rule_evidence = _take(
            [
                entry.item
                for entry in ranked
                if entry.item.citation.relation in {
                    CitationRelation.DIRECT,
                    CitationRelation.GOVERNING_RULE,
                    CitationRelation.PARENT_CONTEXT,
                }
                and entry.item not in exception_evidence
            ],
            self.config.max_primary_items,
        )
        supporting = _take(
            [
                entry.item
                for entry in ranked
                if entry.item not in rule_evidence and entry.item not in exception_evidence and entry.item not in table_evidence
            ],
            self.config.max_supporting_items,
        )
        missing_coverage = _base_missing_coverage(
            [item for item in rule_evidence if item.citation.relation in {CitationRelation.PARENT_CONTEXT, CitationRelation.GOVERNING_RULE}]
        )
        if not exception_evidence:
            missing_coverage.append("No proviso or explanation evidence was selected for the scenario.")
        notes = ["Selected governing rules first, then attached exceptions and explanatory context."]
        return ScenarioEvidencePack(
            pack_type=EvidencePackType.SCENARIO,
            question=result.question,
            query_type=result.query_plan.query_type,
            candidate_chunk_ids=[candidate.chunk.chunk_id for candidate in result.candidates],
            primary_evidence=rule_evidence,
            contextual_evidence=_take(
                [
                    *[item for item in exception_evidence if item not in rule_evidence],
                    *[item for item in table_evidence if item not in rule_evidence],
                ],
                self.config.max_contextual_items,
            ),
            supporting_evidence=supporting,
            missing_coverage=missing_coverage,
            notes=notes,
            metadata={"query_notes": result.query_plan.notes},
            rule_evidence=rule_evidence,
            exception_evidence=exception_evidence,
            table_evidence=table_evidence,
            missing_facts_to_resolve=[],
        )

    def _build_cross_section_pack(self, result: HybridRetrievalResult) -> CrossSectionEvidencePack:
        ranked = _collect_ranked_evidence(result)
        groups = _build_section_groups(ranked, limit=self.config.max_section_groups)
        primary = _take([group.evidence[0] for group in groups if group.evidence], self.config.max_primary_items)
        contextual = _take(
            [
                item
                for group in groups
                for item in group.evidence[1:]
                if item.citation.relation in {CitationRelation.PARENT_CONTEXT, CitationRelation.GOVERNING_RULE}
            ],
            self.config.max_contextual_items,
        )
        supporting = _take(
            [
                item
                for group in groups
                for item in group.evidence
                if item not in primary and item not in contextual
            ],
            self.config.max_supporting_items,
        )
        missing_coverage = _base_missing_coverage(contextual)
        if len(groups) < 2:
            missing_coverage.append("Retrieved evidence does not yet cover multiple linked sections.")
        return CrossSectionEvidencePack(
            pack_type=EvidencePackType.CROSS_SECTION,
            question=result.question,
            query_type=result.query_plan.query_type,
            candidate_chunk_ids=[candidate.chunk.chunk_id for candidate in result.candidates],
            primary_evidence=primary,
            contextual_evidence=contextual,
            supporting_evidence=supporting,
            missing_coverage=missing_coverage,
            notes=["Grouped retrieved evidence by section to support cross-section reasoning."],
            metadata={"query_notes": result.query_plan.notes},
            section_groups=groups,
        )

    def _build_comparison_pack(self, result: HybridRetrievalResult) -> ComparisonEvidencePack:
        ranked = _collect_ranked_evidence(result)
        groups = _build_section_groups(ranked, limit=2)
        primary = _take([group.evidence[0] for group in groups if group.evidence], 2)
        contextual = _take(
            [
                item
                for group in groups
                for item in group.evidence
                if item.citation.relation in {CitationRelation.PARENT_CONTEXT, CitationRelation.GOVERNING_RULE}
            ],
            self.config.max_contextual_items,
        )
        supporting = _take(
            [
                item
                for group in groups
                for item in group.evidence
                if item not in primary and item not in contextual
            ],
            self.config.max_supporting_items,
        )
        missing_coverage = _base_missing_coverage(contextual)
        if len(groups) < 2:
            missing_coverage.append("Comparison evidence does not yet cover two distinct legal sides.")
        return ComparisonEvidencePack(
            pack_type=EvidencePackType.COMPARISON,
            question=result.question,
            query_type=result.query_plan.query_type,
            candidate_chunk_ids=[candidate.chunk.chunk_id for candidate in result.candidates],
            primary_evidence=primary,
            contextual_evidence=contextual,
            supporting_evidence=supporting,
            missing_coverage=missing_coverage,
            notes=["Grouped retrieved evidence into comparison sides for downstream reasoning."],
            metadata={"query_notes": result.query_plan.notes},
            comparison_groups=groups,
        )

    def _build_general_pack(self, result: HybridRetrievalResult) -> EvidencePack:
        ranked = _collect_ranked_evidence(result)
        primary = _take(
            [entry.item for entry in ranked if entry.item.citation.relation is CitationRelation.DIRECT],
            self.config.max_primary_items,
        )
        contextual = _take(
            [
                entry.item
                for entry in ranked
                if entry.item.citation.relation in {CitationRelation.PARENT_CONTEXT, CitationRelation.GOVERNING_RULE}
            ],
            self.config.max_contextual_items,
        )
        supporting = _take(
            [
                entry.item
                for entry in ranked
                if entry.item not in primary and entry.item not in contextual
            ],
            self.config.max_supporting_items,
        )
        return EvidencePack(
            pack_type=EvidencePackType.GENERAL,
            question=result.question,
            query_type=result.query_plan.query_type,
            candidate_chunk_ids=[candidate.chunk.chunk_id for candidate in result.candidates],
            primary_evidence=primary,
            contextual_evidence=contextual,
            supporting_evidence=supporting,
            missing_coverage=_base_missing_coverage(contextual),
            notes=["Built a general evidence pack from reranked hybrid evidence."],
            metadata={"query_notes": result.query_plan.notes},
        )


def build_evidence_pack(
    result: HybridRetrievalResult,
    *,
    config: EvidencePackBuilderConfig | None = None,
) -> EvidencePack:
    return EvidencePackBuilder(config=config).build(result)


def _collect_ranked_evidence(result: HybridRetrievalResult) -> list[_RankedEvidence]:
    ranked: list[_RankedEvidence] = []
    seen: set[tuple[str, CitationRelation]] = set()
    for candidate_index, candidate in enumerate(result.candidates):
        for item in candidate.evidence:
            key = (item.node_id, item.citation.relation)
            if key in seen:
                continue
            ranked.append(_RankedEvidence(item=item, candidate_index=candidate_index, candidate=candidate))
            seen.add(key)
    for item in result.evidence:
        key = (item.node_id, item.citation.relation)
        if key in seen:
            continue
        ranked.append(_RankedEvidence(item=item, candidate_index=len(result.candidates), candidate=None))
        seen.add(key)
    return ranked


def _build_section_groups(
    ranked: list[_RankedEvidence],
    *,
    limit: int,
) -> list[SectionEvidenceGroup]:
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    ordered_sections: list[str] = []
    for entry in ranked:
        section_number = entry.item.citation.section_number or "unscoped"
        if section_number not in grouped:
            ordered_sections.append(section_number)
        grouped[section_number].append(entry.item)

    groups: list[SectionEvidenceGroup] = []
    for section_number in ordered_sections[:limit]:
        evidence = _dedupe_evidence(grouped[section_number])
        if not evidence:
            continue
        groups.append(
            SectionEvidenceGroup(
                label=_group_label(section_number, evidence[0]),
                section_number=None if section_number == "unscoped" else section_number,
                evidence=evidence,
            )
        )
    return groups


def _group_label(section_number: str, item: EvidenceItem) -> str:
    if section_number != "unscoped":
        return f"Section {section_number}"
    return item.citation.citability_label or item.node_id


def _first_section_number(items: list[EvidenceItem]) -> str | None:
    for item in items:
        if item.citation.section_number:
            return item.citation.section_number
    return None


def _is_table_like(entry: _RankedEvidence) -> bool:
    item = entry.item
    if item.citation.relation is CitationRelation.ATTACHED_TABLE:
        return True
    if _node_type(item) == "table":
        return True
    if entry.candidate is None:
        return False
    return entry.candidate.chunk.chunk_variant == "table_row" or entry.candidate.chunk.source_node_type.value == "table"


def _node_type(item: EvidenceItem) -> str:
    return str(item.metadata.get("node_type") or "").lower()


def _base_missing_coverage(contextual_items: list[EvidenceItem]) -> list[str]:
    if contextual_items:
        return []
    return ["Linked parent or governing context was not found in the selected evidence."]


def _dedupe_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    deduped: list[EvidenceItem] = []
    seen: set[tuple[str, CitationRelation]] = set()
    for item in items:
        key = (item.node_id, item.citation.relation)
        if key in seen:
            continue
        deduped.append(item)
        seen.add(key)
    return deduped


def _take(items: list[EvidenceItem], limit: int) -> list[EvidenceItem]:
    return _dedupe_evidence(items)[:limit]
