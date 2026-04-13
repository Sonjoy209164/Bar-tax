import pytest
from pydantic import ValidationError

from app.domain import CitationRelation, LegalCitation, QueryExecutionPath, QueryType
from app.reasoning import AgentState, QueryPlanStep, RetrievalAttempt, VerificationFailure
from app.domain.models import EvidenceItem


def _citation(node_id: str, section_number: str = "4") -> LegalCitation:
    return LegalCitation(
        node_id=node_id,
        document_id="income-tax-act-2023",
        act_title="Income Tax Act 2023",
        relation=CitationRelation.DIRECT,
        section_number=section_number,
        page_start=24,
        page_end=24,
    )


def _evidence(evidence_id: str, node_id: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        node_id=node_id,
        citation=_citation(node_id),
        source_text="The National Board of Revenue.",
        score=0.9,
        retrieval_method="hybrid",
    )


def test_agent_state_defaults_are_langgraph_ready() -> None:
    state = AgentState(
        question="What are the income tax authorities under section 4?",
        query_type=QueryType.SECTION_LOOKUP,
        execution_path=QueryExecutionPath.FAST_PATH,
    )

    assert state.trace_id
    assert state.remaining_steps == 4
    assert state.exhausted_reasoning_budget is False
    assert state.should_enter_agent_loop is False


def test_agent_state_agentic_route_exposes_loop_flag() -> None:
    state = AgentState(
        question="I am a labour, what will be my tax?",
        query_type=QueryType.ELIGIBILITY,
        execution_path=QueryExecutionPath.AGENTIC,
    )

    assert state.should_enter_agent_loop is True


def test_advance_step_tracks_budget_and_completed_nodes() -> None:
    state = AgentState(question="Q", max_reasoning_steps=2)

    state.advance_step("router")
    state.advance_step("planner")

    assert state.current_step == 2
    assert state.completed_nodes == ["router", "planner"]
    assert state.remaining_steps == 0
    assert state.exhausted_reasoning_budget is True


def test_advance_step_rejects_empty_name_and_budget_overflow() -> None:
    state = AgentState(question="Q", max_reasoning_steps=1)

    with pytest.raises(ValueError):
        state.advance_step("   ")

    state.advance_step("router")

    with pytest.raises(ValueError):
        state.advance_step("planner")


def test_agent_state_rejects_invalid_initial_step_budget() -> None:
    with pytest.raises(ValidationError):
        AgentState(question="Q", current_step=5, max_reasoning_steps=4)


def test_add_retrieval_attempt_updates_more_retrieval_flag() -> None:
    state = AgentState(question="Q")
    attempt = RetrievalAttempt(
        attempt_number=1,
        query_text="section 4 income tax authorities",
        retrieval_mode="hybrid",
        requires_more_retrieval=True,
    )

    state.add_retrieval_attempt(attempt)

    assert state.needs_more_retrieval is True
    assert state.retrieval_attempts == [attempt]


def test_add_evidence_deduplicates_evidence_and_citations() -> None:
    state = AgentState(question="Q")
    first = _evidence("e1", "node-1")
    duplicate = _evidence("e1", "node-1")
    sibling = _evidence("e2", "node-2")

    state.add_evidence([first, duplicate, sibling])

    assert [item.evidence_id for item in state.retrieved_evidence] == ["e1", "e2"]
    assert [citation.node_id for citation in state.citations] == ["node-1", "node-2"]


def test_add_fact_helpers_keep_unique_reasoning_state() -> None:
    state = AgentState(question="Q")

    state.add_fact_found("Director is treated as employee.")
    state.add_fact_found("Director is treated as employee.")
    state.add_missing_fact("Annual income is not provided.")
    state.add_missing_fact("Annual income is not provided.")
    state.add_rule_found("Section 32 covers income from employment.")
    state.add_exception_found("Day labourer is excluded from employee definition.")
    state.add_open_issue("Need resident status.")
    state.add_reasoning_note("Eligibility question requires missing-fact handling.")

    assert state.facts_found == ["Director is treated as employee."]
    assert state.missing_facts == ["Annual income is not provided."]
    assert state.rules_found == ["Section 32 covers income from employment."]
    assert state.exceptions_found == ["Day labourer is excluded from employee definition."]
    assert state.open_issues == ["Need resident status."]
    assert state.reasoning_summary == ["Eligibility question requires missing-fact handling."]


def test_verification_failure_sets_error_flag() -> None:
    state = AgentState(question="Q", draft_answer="Draft answer")
    failure = VerificationFailure(
        claim_text="The tax rate is 20%.",
        reason="20% does not appear in retrieved evidence.",
        severity="error",
        evidence_ids=["e1"],
    )

    state.add_verification_failure(failure)

    assert state.has_verification_errors is True
    assert state.ready_for_compose is True


def test_query_plan_step_requires_non_empty_text() -> None:
    with pytest.raises(ValidationError):
        QueryPlanStep(goal="  ", sub_query="section 4")
