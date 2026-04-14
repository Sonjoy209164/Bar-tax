from enum import StrEnum

from pydantic import BaseModel, Field


class QueryType(StrEnum):
    GENERAL = "general"
    SECTION_LOOKUP = "section_lookup"
    DEFINITION = "definition"
    TABLE_LOOKUP = "table_lookup"
    RATE_LOOKUP = "rate_lookup"
    AMOUNT_LOOKUP = "amount_lookup"
    DATE_LOOKUP = "date_lookup"
    DURATION_LOOKUP = "duration_lookup"
    COUNT_LOOKUP = "count_lookup"
    LIST_LOOKUP = "list_lookup"
    MENTION_LOOKUP = "mention_lookup"
    COMPARISON = "comparison"
    SCENARIO_REASONING = "scenario_reasoning"
    CROSS_SECTION_REASONING = "cross_section_reasoning"
    ELIGIBILITY = "eligibility"
    AMENDMENT = "amendment"
    EXAMPLE = "example"
    PROCEDURE = "procedure"
    CALCULATION = "calculation"
    UNSUPPORTED_OR_UNDERSPECIFIED = "unsupported_or_underspecified"


class QueryExecutionPath(StrEnum):
    FAST_PATH = "fast_path"
    AGENTIC = "agentic"
    CLARIFICATION = "clarification"


QUERY_TYPE_ALIASES: dict[str, QueryType] = {
    "general": QueryType.GENERAL,
    "section": QueryType.SECTION_LOOKUP,
    "section_lookup": QueryType.SECTION_LOOKUP,
    "definition": QueryType.DEFINITION,
    "table_lookup": QueryType.TABLE_LOOKUP,
    "rate_lookup": QueryType.RATE_LOOKUP,
    "amount_lookup": QueryType.AMOUNT_LOOKUP,
    "date_lookup": QueryType.DATE_LOOKUP,
    "duration_lookup": QueryType.DURATION_LOOKUP,
    "count_lookup": QueryType.COUNT_LOOKUP,
    "list_lookup": QueryType.LIST_LOOKUP,
    "mention_lookup": QueryType.MENTION_LOOKUP,
    "comparison": QueryType.COMPARISON,
    "scenario_reasoning": QueryType.SCENARIO_REASONING,
    "cross_section_reasoning": QueryType.CROSS_SECTION_REASONING,
    "eligibility": QueryType.ELIGIBILITY,
    "amendment": QueryType.AMENDMENT,
    "example": QueryType.EXAMPLE,
    "procedure": QueryType.PROCEDURE,
    "calculation": QueryType.CALCULATION,
    "unsupported_or_underspecified": QueryType.UNSUPPORTED_OR_UNDERSPECIFIED,
}

FAST_PATH_QUERY_TYPES = frozenset(
    {
        QueryType.GENERAL,
        QueryType.SECTION_LOOKUP,
        QueryType.DEFINITION,
        QueryType.TABLE_LOOKUP,
        QueryType.RATE_LOOKUP,
        QueryType.AMOUNT_LOOKUP,
        QueryType.DATE_LOOKUP,
        QueryType.DURATION_LOOKUP,
        QueryType.COUNT_LOOKUP,
        QueryType.LIST_LOOKUP,
        QueryType.MENTION_LOOKUP,
        QueryType.AMENDMENT,
        QueryType.EXAMPLE,
        QueryType.PROCEDURE,
        QueryType.CALCULATION,
    }
)

AGENTIC_QUERY_TYPES = frozenset(
    {
        QueryType.COMPARISON,
        QueryType.SCENARIO_REASONING,
        QueryType.CROSS_SECTION_REASONING,
        QueryType.ELIGIBILITY,
    }
)

CLARIFICATION_QUERY_TYPES = frozenset({QueryType.UNSUPPORTED_OR_UNDERSPECIFIED})


class QueryTaxonomyDecision(BaseModel):
    query_type: QueryType
    execution_path: QueryExecutionPath
    use_agent_loop: bool
    requires_parent_context: bool = True
    requires_missing_fact_check: bool = False
    requires_table_reasoning: bool = False
    requires_cross_section_expansion: bool = False
    notes: list[str] = Field(default_factory=list)


def canonicalize_query_type(value: str | QueryType | None) -> QueryType:
    if isinstance(value, QueryType):
        return value
    if value is None:
        return QueryType.GENERAL
    return QUERY_TYPE_ALIASES.get(value, QueryType.GENERAL)


def infer_execution_path(query_type: str | QueryType) -> QueryExecutionPath:
    canonical = canonicalize_query_type(query_type)
    if canonical in AGENTIC_QUERY_TYPES:
        return QueryExecutionPath.AGENTIC
    if canonical in CLARIFICATION_QUERY_TYPES:
        return QueryExecutionPath.CLARIFICATION
    return QueryExecutionPath.FAST_PATH


def build_query_taxonomy_decision(query_type: str | QueryType) -> QueryTaxonomyDecision:
    canonical = canonicalize_query_type(query_type)
    execution_path = infer_execution_path(canonical)
    requires_missing_fact_check = canonical in {
        QueryType.ELIGIBILITY,
        QueryType.SCENARIO_REASONING,
        QueryType.CROSS_SECTION_REASONING,
        QueryType.COMPARISON,
        QueryType.UNSUPPORTED_OR_UNDERSPECIFIED,
    }
    requires_table_reasoning = canonical in {QueryType.TABLE_LOOKUP, QueryType.RATE_LOOKUP}
    requires_cross_section_expansion = canonical in {
        QueryType.SECTION_LOOKUP,
        QueryType.COMPARISON,
        QueryType.SCENARIO_REASONING,
        QueryType.CROSS_SECTION_REASONING,
        QueryType.ELIGIBILITY,
    }
    notes: list[str] = []
    if execution_path is QueryExecutionPath.AGENTIC:
        notes.append("Use bounded agentic reasoning with explicit state tracking.")
    if execution_path is QueryExecutionPath.CLARIFICATION:
        notes.append("Require clarification or refuse unsupported claims.")
    if requires_table_reasoning:
        notes.append("Preserve table rows and linked governing rules in evidence packs.")
    if canonical is QueryType.ELIGIBILITY:
        notes.append("Check for missing user facts before concluding tax applicability.")
    return QueryTaxonomyDecision(
        query_type=canonical,
        execution_path=execution_path,
        use_agent_loop=execution_path is QueryExecutionPath.AGENTIC,
        requires_parent_context=True,
        requires_missing_fact_check=requires_missing_fact_check,
        requires_table_reasoning=requires_table_reasoning,
        requires_cross_section_expansion=requires_cross_section_expansion,
        notes=notes,
    )
