from app.domain import CitationRelation, EvidenceItem, LegalCitation, QueryExecutionPath, QueryType
from app.reasoning import AgentState, RetrievalAttempt, apply_prompt_strategy, build_safe_reasoning_trace
from app.reasoning.nli_guardrail import verify_draft_answer
from app.services import QueryRequest


def _evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="e1",
        node_id="income-tax-paripatra-2025-2026:section:2-1",
        citation=LegalCitation(
            node_id="income-tax-paripatra-2025-2026:section:2-1",
            document_id="income-tax-paripatra-2025-2026",
            act_title="আয়কর পরিপত্র ২০২৫-২০২৬",
            relation=CitationRelation.DIRECT,
            section_number="2.1",
            page_start=4,
            page_end=4,
            citability_label="Section 2.1",
        ),
        source_text="মোট আয় করহার প্রথম ৩,৫০,০০০ টাকা পর্যন্ত মোট আয়ের উপর শূন্য। পরবর্তী ১,০০,০০০ টাকা পর্যন্ত ৫%।",
        score=0.92,
        retrieval_method="hybrid",
    )


def test_query_request_normalizes_prompt_strategy_and_trace_mode() -> None:
    request = QueryRequest(
        question="২০২৫-২০২৬ করবর্ষে করহার কী?",
        prompt_strategy="Few Shot",
        reasoning_trace_mode="cot",
    )

    assert request.prompt_strategy == "few_shot"
    assert request.reasoning_trace_mode == "trace"
    assert request.query_type is QueryType.RATE_LOOKUP


def test_few_shot_strategy_formats_answer_without_breaking_guardrail() -> None:
    evidence = _evidence()
    state = AgentState(
        question="২০২৫-২০২৬ করবর্ষে স্বাভাবিক ব্যক্তির করহার কী?",
        query_type=QueryType.RATE_LOOKUP,
        execution_path=QueryExecutionPath.FAST_PATH,
        prompt_strategy="few_shot",
        rules_found=["Section 2.1"],
        citations=[evidence.citation],
    )

    answer = apply_prompt_strategy("প্রথম ৩,৫০,০০০ টাকা পর্যন্ত মোট আয়ের উপর শূন্য।", state=state, evidence_items=[evidence])
    verification = verify_draft_answer(answer, evidence_items=[evidence], query_type=QueryType.RATE_LOOKUP)

    assert answer.startswith("সংক্ষিপ্ত উত্তর:")
    assert "প্রযোজ্য বিধান: Section 2.1" in answer
    assert state.trace_metadata["prompt_examples_used"] == [
        "bangla_tax_direct_rate_lookup",
        "bangla_tax_missing_fact_check",
        "bangla_tax_exception_check",
    ]
    assert verification.has_errors is False


def test_safe_reasoning_trace_omits_private_answer_text() -> None:
    state = AgentState(
        question="২০২৫-২০২৬ করবর্ষে করহার কী?",
        query_type=QueryType.RATE_LOOKUP,
        execution_path=QueryExecutionPath.FAST_PATH,
        prompt_strategy="one_shot",
        reasoning_trace_mode="trace",
        draft_answer="private draft answer",
        final_answer="private final answer",
    )
    state.completed_nodes = ["router", "planner", "retrieve", "reason"]
    state.latest_selected_evidence_ids = ["e1"]
    state.trace_metadata["prompt_examples_used"] = ["bangla_tax_direct_rate_lookup"]
    state.trace_metadata["private_scratchpad"] = "do not expose"
    state.add_retrieval_attempt(
        RetrievalAttempt(
            attempt_number=1,
            query_text="করহার",
            candidate_evidence_ids=["e1", "e2"],
            selected_evidence_ids=["e1"],
        )
    )

    trace = build_safe_reasoning_trace(state, "trace")

    assert trace["mode"] == "trace"
    assert trace["prompt_strategy"] == "one_shot"
    assert trace["retrieval_attempts"][0]["selected_evidence_ids"] == ["e1"]
    assert "draft_answer" not in trace
    assert "final_answer" not in trace
    assert "private_scratchpad" not in trace["trace_metadata"]


def test_reasoning_trace_off_returns_empty_payload() -> None:
    state = AgentState(question="Q", reasoning_trace_mode="off")

    assert build_safe_reasoning_trace(state, state.reasoning_trace_mode) == {}
