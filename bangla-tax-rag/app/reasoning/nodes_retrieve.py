from __future__ import annotations

from app.reasoning.evidence_builder import AgentEvidenceBuilder, AgentEvidenceBuildResult, apply_evidence_build_result
from app.reasoning.state import AgentState, RetrievalAttempt
from app.retrieval import HybridRetriever, HybridSearchRequest


def run_retrieve_node(
    state: AgentState,
    *,
    hybrid_retriever: HybridRetriever,
    evidence_builder: AgentEvidenceBuilder | None = None,
    top_k: int | None = None,
) -> tuple[AgentState, AgentEvidenceBuildResult]:
    if state.exhausted_reasoning_budget:
        state.add_open_issue("Reasoning budget exhausted before retrieve step.")
        return state, AgentEvidenceBuildResult.model_validate({"pack": _empty_pack(state)})

    state.advance_step("retrieve")
    effective_top_k = top_k or min(5 + len(state.retrieval_attempts), 8)
    retrieval_result = hybrid_retriever.search(
        HybridSearchRequest(
            question=state.question,
            top_k=effective_top_k,
            query_type=state.query_type,
        )
    )

    built = (evidence_builder or AgentEvidenceBuilder()).build(retrieval_result)
    apply_evidence_build_result(state, built)

    attempt_number = len(state.retrieval_attempts) + 1
    requires_more_retrieval = bool(
        built.missing_coverage
        and state.should_enter_agent_loop
        and attempt_number < 2
    )
    state.add_retrieval_attempt(
        RetrievalAttempt(
            attempt_number=attempt_number,
            query_text=state.normalized_question or state.question,
            retrieval_mode="hybrid",
            candidate_evidence_ids=[item.evidence_id for item in retrieval_result.evidence],
            selected_evidence_ids=list(built.selected_evidence_ids),
            notes=[*built.pack.notes, *built.missing_coverage],
            requires_more_retrieval=requires_more_retrieval,
        )
    )
    state.trace_metadata["latest_retrieval_top_k"] = effective_top_k
    state.trace_metadata["latest_retrieval_candidate_count"] = len(retrieval_result.candidates)
    return state, built


def _empty_pack(state: AgentState) -> dict:
    return {
        "pack_type": "general",
        "question": state.question,
        "query_type": state.query_type,
        "candidate_chunk_ids": [],
        "primary_evidence": [],
        "contextual_evidence": [],
        "supporting_evidence": [],
        "missing_coverage": ["No evidence retrieved."],
        "notes": ["Retrieval returned no evidence."],
        "metadata": {},
    }
