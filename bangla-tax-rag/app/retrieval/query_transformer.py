from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, Field, model_validator

from app.core.utils import (
    detect_query_type,
    extract_definition_target,
    extract_informative_query_terms,
    extract_query_section_references,
    normalize_text,
    rewrite_query,
)
from app.domain import QueryExecutionPath, QueryType, build_query_taxonomy_decision, canonicalize_query_type
from app.reasoning import QueryPlanStep

SCENARIO_MARKERS = (
    " if ",
    " when ",
    " where ",
    " scenario ",
    " for a ",
    " for an ",
    " as a ",
    " benefit ",
    " allowance ",
    " perquisite ",
)
ROLE_TERMS = {
    "director": ["director", "managing director", "employee"],
    "employee": ["employee", "employment", "income from employment"],
    "labourer": ["labourer", "worker", "day labourer", "employee"],
    "worker": ["worker", "labourer", "employee", "employment"],
    "startup": ["startup", "registered startup", "sandbox"],
    "company": ["company", "assessee", "taxpayer"],
}
ASSET_AND_RULE_EXPANSIONS = {
    "car benefit": ["perquisite", "motor vehicle", "vehicle valuation table"],
    "car": ["motor vehicle", "vehicle valuation table", "perquisite"],
    "motor vehicle": ["vehicle valuation table", "perquisite", "benefit"],
    "stock dividend": ["dividend", "bonus share", "rate of tax"],
    "tax day": ["due date", "filing deadline", "return submission date"],
    "commissioner": ["commissioner of taxes", "large assessee unit", "definition"],
    "tea and rubber": ["income from agriculture", "agricultural income", "business income"],
    "agricultural income": ["income from agriculture", "tea and rubber", "section 40"],
    "charitable purpose": ["general public utility", "services for consideration", "threshold amount"],
}


class QueryTransformerConfig(BaseModel):
    min_sub_queries: int = Field(default=3, ge=1, le=10)
    max_sub_queries: int = Field(default=5, ge=1, le=12)
    include_section_disambiguation: bool = True
    include_legal_term_expansion: bool = True
    include_scenario_decomposition: bool = True

    @model_validator(mode="after")
    def validate_bounds(self) -> "QueryTransformerConfig":
        if self.min_sub_queries > self.max_sub_queries:
            raise ValueError("min_sub_queries cannot exceed max_sub_queries")
        return self


class QueryPlan(BaseModel):
    question: str
    normalized_question: str
    query_type: QueryType
    execution_path: QueryExecutionPath
    section_references: list[str] = Field(default_factory=list)
    focus_terms: list[str] = Field(default_factory=list)
    legal_expansions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    steps: list[QueryPlanStep] = Field(default_factory=list)


class QueryTransformer:
    def __init__(self, config: QueryTransformerConfig | None = None) -> None:
        self.config = config or QueryTransformerConfig()

    def transform(self, question: str, *, query_type: str | QueryType | None = None) -> QueryPlan:
        normalized_question = normalize_text(question)
        inferred_query_type = canonicalize_query_type(query_type or detect_query_type(normalized_question))
        if inferred_query_type is QueryType.GENERAL and _is_scenario_like(normalized_question):
            inferred_query_type = QueryType.SCENARIO_REASONING

        taxonomy = build_query_taxonomy_decision(inferred_query_type)
        section_references = extract_query_section_references(normalized_question)
        definition_target = extract_definition_target(normalized_question)
        focus_terms = _ordered_unique(
            [
                *extract_informative_query_terms(normalized_question, inferred_query_type),
                *(extract_informative_query_terms(definition_target, QueryType.DEFINITION) if definition_target else []),
            ]
        )
        legal_expansions = _expand_legal_terms(
            normalized_question,
            focus_terms=focus_terms,
            definition_target=definition_target,
            query_type=inferred_query_type,
        )

        steps: list[QueryPlanStep] = []
        notes = list(taxonomy.notes)

        steps.append(
            QueryPlanStep(
                goal="primary retrieval query",
                sub_query=rewrite_query(normalized_question, inferred_query_type),
                rationale="Use a normalized, legal-term-aware rewrite as the primary retrieval handle.",
                preferred_node_types=_preferred_node_types_for_query_type(inferred_query_type),
                metadata_filters=_section_filter(section_references[0] if section_references else None),
            )
        )

        if definition_target:
            steps.extend(_definition_steps(definition_target, section_references))
        if self.config.include_section_disambiguation and section_references:
            steps.extend(_section_disambiguation_steps(normalized_question, focus_terms, section_references))
        if self.config.include_legal_term_expansion and legal_expansions:
            steps.extend(_expansion_steps(normalized_question, legal_expansions, inferred_query_type, section_references))
        if self.config.include_scenario_decomposition and _is_scenario_like(normalized_question):
            scenario_steps = _scenario_steps(normalized_question, section_references)
            if scenario_steps:
                notes.append("Scenario-like wording detected; decomposed into role/rule/value sub-queries.")
                steps.extend(scenario_steps)
        if inferred_query_type is QueryType.COMPARISON:
            steps.extend(_comparison_steps(normalized_question, section_references))
        if inferred_query_type in {QueryType.TABLE_LOOKUP, QueryType.RATE_LOOKUP}:
            steps.extend(_table_rate_steps(normalized_question, section_references))

        finalized_steps = _deduplicate_steps(steps)[: self.config.max_sub_queries]
        finalized_steps = _ensure_minimum_steps(
            finalized_steps,
            min_count=self.config.min_sub_queries,
            normalized_question=normalized_question,
            query_type=inferred_query_type,
            section_references=section_references,
            focus_terms=focus_terms,
            legal_expansions=legal_expansions,
        )

        return QueryPlan(
            question=question,
            normalized_question=normalized_question,
            query_type=inferred_query_type,
            execution_path=taxonomy.execution_path,
            section_references=section_references,
            focus_terms=focus_terms,
            legal_expansions=legal_expansions,
            notes=_ordered_unique(notes),
            steps=finalized_steps[: self.config.max_sub_queries],
        )


def build_query_plan(
    question: str,
    *,
    query_type: str | QueryType | None = None,
    config: QueryTransformerConfig | None = None,
) -> QueryPlan:
    return QueryTransformer(config=config).transform(question, query_type=query_type)


def _is_scenario_like(normalized_question: str) -> bool:
    padded = f" {normalized_question.lower()} "
    return any(marker in padded for marker in SCENARIO_MARKERS)


def _expand_legal_terms(
    normalized_question: str,
    *,
    focus_terms: list[str],
    definition_target: str | None,
    query_type: QueryType,
) -> list[str]:
    expansions: list[str] = []
    lowered = normalized_question.lower()
    if definition_target:
        expansions.extend(token for token in [definition_target, f'"{definition_target}" means'] if token)
    for phrase, phrase_expansions in ASSET_AND_RULE_EXPANSIONS.items():
        if phrase in lowered:
            expansions.extend(phrase_expansions)
    for role, role_expansions in ROLE_TERMS.items():
        if role in lowered:
            expansions.extend(role_expansions)
    if query_type in {QueryType.TABLE_LOOKUP, QueryType.RATE_LOOKUP}:
        expansions.extend(["table", "rate of tax", "governing rule"])
    if query_type is QueryType.COMPARISON:
        expansions.extend(["compare", "difference", "other than company"])
    if query_type is QueryType.ELIGIBILITY:
        expansions.extend(["chargeable to tax", "tax exemption", "assessee"])
    expansions.extend(focus_terms)
    return _ordered_unique(item for item in expansions if item and item.strip())


def _definition_steps(definition_target: str, section_references: list[str]) -> list[QueryPlanStep]:
    section_reference = section_references[0] if section_references else None
    filters = _section_filter(section_reference)
    return [
        QueryPlanStep(
            goal="exact definition lookup",
            sub_query=f"definition of {definition_target}",
            rationale="Definition questions need the definitional label and target term together.",
            preferred_node_types=["definition", "section", "clause"],
            metadata_filters=filters,
        ),
        QueryPlanStep(
            goal="quoted definition pattern",
            sub_query=f'"{definition_target}" means',
            rationale="Definitions in statutes often appear in a quoted-term-means pattern.",
            preferred_node_types=["definition", "clause"],
            metadata_filters=filters,
        ),
    ]


def _section_disambiguation_steps(
    normalized_question: str,
    focus_terms: list[str],
    section_references: list[str],
) -> list[QueryPlanStep]:
    primary_section = section_references[0]
    focus_phrase = " ".join(focus_terms[:4]).strip() or normalized_question
    return [
        QueryPlanStep(
            goal="section-targeted retrieval",
            sub_query=f"section {primary_section} {focus_phrase}".strip(),
            rationale="Pin the query to the cited section before letting semantic retrieval expand it.",
            preferred_node_types=["section", "subsection", "clause"],
            metadata_filters=_section_filter(primary_section),
        ),
        QueryPlanStep(
            goal="section heading disambiguation",
            sub_query=f"{focus_phrase} under section {primary_section}".strip(),
            rationale="Recover the section heading and local clause neighborhood for the cited section.",
            preferred_node_types=["section", "subsection"],
            metadata_filters=_section_filter(primary_section),
        ),
    ]


def _expansion_steps(
    normalized_question: str,
    legal_expansions: list[str],
    query_type: QueryType,
    section_references: list[str],
) -> list[QueryPlanStep]:
    primary_section = section_references[0] if section_references else None
    chosen_terms = " ".join(legal_expansions[:3]).strip()
    if not chosen_terms:
        return []
    sub_query = f"{chosen_terms} {normalized_question}".strip()
    return [
        QueryPlanStep(
            goal="legal terminology expansion",
            sub_query=sub_query,
            rationale="Expand the user wording into the legal vocabulary likely used in the Act.",
            preferred_node_types=_preferred_node_types_for_query_type(query_type),
            metadata_filters=_section_filter(primary_section),
        )
    ]


def _scenario_steps(normalized_question: str, section_references: list[str]) -> list[QueryPlanStep]:
    lowered = normalized_question.lower()
    primary_section = section_references[0] if section_references else None
    scenario_queries: list[QueryPlanStep] = []

    detected_roles = [role for role in ROLE_TERMS if role in lowered]
    for role in detected_roles[:2]:
        scenario_queries.append(
            QueryPlanStep(
                goal="role definition and coverage",
                sub_query=f"definition of {role}",
                rationale="Scenario questions often hinge on whether a role falls inside a defined taxpayer or employee category.",
                preferred_node_types=["definition", "section", "clause"],
                metadata_filters=_section_filter(primary_section),
            )
        )

    if "car" in lowered or "motor vehicle" in lowered:
        scenario_queries.extend(
            [
                QueryPlanStep(
                    goal="perquisite rule retrieval",
                    sub_query="perquisite director motor vehicle",
                    rationale="Car-benefit scenarios usually turn on perquisite rules attached to employment income.",
                    preferred_node_types=["section", "clause", "table"],
                    metadata_filters=_section_filter(primary_section),
                ),
                QueryPlanStep(
                    goal="vehicle valuation table retrieval",
                    sub_query="motor vehicle valuation table",
                    rationale="Vehicle benefits typically require both the rule and the valuation table.",
                    preferred_node_types=["table", "section", "clause"],
                    metadata_filters=_section_filter(primary_section),
                ),
            ]
        )
    elif "benefit" in lowered or "allowance" in lowered:
        scenario_queries.append(
            QueryPlanStep(
                goal="benefit-to-rule decomposition",
                sub_query="perquisite allowance rule",
                rationale="Translate benefit wording into the statutory rule category that likely governs the scenario.",
                preferred_node_types=["section", "clause", "definition"],
                metadata_filters=_section_filter(primary_section),
            )
        )
    return scenario_queries


def _comparison_steps(normalized_question: str, section_references: list[str]) -> list[QueryPlanStep]:
    primary_section = section_references[0] if section_references else None
    lowered = normalized_question.lower()
    if "company" in lowered and re.search(r"other than\s+(?:a\s+)?company", lowered):
        return [
            QueryPlanStep(
                goal="first comparison side",
                sub_query="company " + normalized_question,
                rationale="Split the comparison into the first statutory subject.",
                preferred_node_types=["section", "clause", "table"],
                metadata_filters=_section_filter(primary_section),
            ),
            QueryPlanStep(
                goal="second comparison side",
                sub_query="other than company " + normalized_question,
                rationale="Split the comparison into the contrasting statutory subject.",
                preferred_node_types=["section", "clause", "table"],
                metadata_filters=_section_filter(primary_section),
            ),
        ]
    return [
        QueryPlanStep(
            goal="comparison-side decomposition",
            sub_query=f"compare separate sides {normalized_question}",
            rationale="Comparison questions benefit from decomposing each side before evidence assembly.",
            preferred_node_types=["section", "clause", "table"],
            metadata_filters=_section_filter(primary_section),
        )
    ]


def _table_rate_steps(normalized_question: str, section_references: list[str]) -> list[QueryPlanStep]:
    primary_section = section_references[0] if section_references else None
    filters = _section_filter(primary_section)
    return [
        QueryPlanStep(
            goal="table lookup",
            sub_query=f"table {normalized_question}",
            rationale="Rate questions often require a table row rather than free text alone.",
            preferred_node_types=["table", "clause", "section"],
            metadata_filters=filters,
        ),
        QueryPlanStep(
            goal="governing rule lookup",
            sub_query=f"rate of tax {normalized_question}",
            rationale="Retrieve the governing rule that explains how to read the table value.",
            preferred_node_types=["section", "clause", "table"],
            metadata_filters=filters,
        ),
    ]


def _ensure_minimum_steps(
    steps: list[QueryPlanStep],
    *,
    min_count: int,
    normalized_question: str,
    query_type: QueryType,
    section_references: list[str],
    focus_terms: list[str],
    legal_expansions: list[str],
) -> list[QueryPlanStep]:
    if len(steps) >= min_count:
        return steps

    primary_section = section_references[0] if section_references else None
    fallback_queries = [
        normalized_question,
        " ".join(focus_terms[:4]).strip(),
        " ".join(legal_expansions[:4]).strip(),
    ]
    for fallback_query in fallback_queries:
        if len(steps) >= min_count:
            break
        if not fallback_query:
            continue
        steps.append(
            QueryPlanStep(
                goal="fallback focused retrieval",
                sub_query=fallback_query,
                rationale="Ensure the retriever gets a bounded set of focused alternatives even when decomposition is light.",
                preferred_node_types=_preferred_node_types_for_query_type(query_type),
                metadata_filters=_section_filter(primary_section),
            )
        )
        steps = _deduplicate_steps(steps)
    return steps


def _preferred_node_types_for_query_type(query_type: QueryType) -> list[str]:
    if query_type is QueryType.DEFINITION:
        return ["definition", "section", "clause"]
    if query_type in {QueryType.TABLE_LOOKUP, QueryType.RATE_LOOKUP}:
        return ["table", "section", "clause"]
    if query_type in {QueryType.SECTION_LOOKUP, QueryType.CROSS_SECTION_REASONING}:
        return ["section", "subsection", "clause", "proviso", "explanation"]
    if query_type in {QueryType.COMPARISON, QueryType.SCENARIO_REASONING, QueryType.ELIGIBILITY}:
        return ["section", "clause", "proviso", "explanation", "table", "definition"]
    return ["section", "clause", "definition"]


def _section_filter(section_reference: str | None) -> dict[str, str]:
    return {"section_number": section_reference} if section_reference else {}


def _deduplicate_steps(steps: Iterable[QueryPlanStep]) -> list[QueryPlanStep]:
    deduped: list[QueryPlanStep] = []
    seen: set[tuple[str, tuple[tuple[str, str | int | float | bool | None], ...]]] = set()
    for step in steps:
        key = (
            step.sub_query.strip().lower(),
            tuple(sorted(step.metadata_filters.items())),
        )
        if key in seen:
            continue
        deduped.append(step)
        seen.add(key)
    return deduped


def _ordered_unique(values: Iterable[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        items.append(cleaned)
        seen.add(lowered)
    return items
