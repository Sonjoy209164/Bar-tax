from app.core.utils import preprocess_query
from app.domain.query_taxonomy import (
    QueryExecutionPath,
    QueryType,
    build_query_taxonomy_decision,
    canonicalize_query_type,
    infer_execution_path,
)


def test_canonicalize_query_type_returns_section_lookup_for_alias() -> None:
    assert canonicalize_query_type("section") is QueryType.SECTION_LOOKUP


def test_fast_path_query_type_routes_without_agent_loop() -> None:
    decision = build_query_taxonomy_decision(QueryType.DEFINITION)

    assert decision.execution_path is QueryExecutionPath.FAST_PATH
    assert decision.use_agent_loop is False
    assert decision.requires_parent_context is True


def test_agentic_query_type_routes_to_bounded_agent_loop() -> None:
    decision = build_query_taxonomy_decision(QueryType.SCENARIO_REASONING)

    assert decision.execution_path is QueryExecutionPath.AGENTIC
    assert decision.use_agent_loop is True
    assert decision.requires_missing_fact_check is True


def test_clarification_query_type_routes_to_clarification_path() -> None:
    assert infer_execution_path(QueryType.UNSUPPORTED_OR_UNDERSPECIFIED) is QueryExecutionPath.CLARIFICATION


def test_rate_lookup_marks_table_reasoning_requirement() -> None:
    decision = build_query_taxonomy_decision(QueryType.RATE_LOOKUP)

    assert decision.requires_table_reasoning is True
    assert any("table rows" in note.lower() for note in decision.notes)


def test_preprocess_query_exposes_execution_path_for_existing_query_types() -> None:
    signals = preprocess_query("I am a labour, what will be my tax?")

    assert signals.query_type is QueryType.ELIGIBILITY
    assert signals.query_intent is QueryType.ELIGIBILITY
    assert signals.execution_path is QueryExecutionPath.AGENTIC


def test_preprocess_query_keeps_definition_on_fast_path() -> None:
    signals = preprocess_query("What is the definition of Commissioner?")

    assert signals.query_type is QueryType.DEFINITION
    assert signals.execution_path is QueryExecutionPath.FAST_PATH
