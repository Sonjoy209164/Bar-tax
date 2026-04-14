from __future__ import annotations

from app.reasoning.answer_policy import apply_answer_policy
from app.reasoning.evidence_builder import AgentEvidenceBuildResult
from app.reasoning.nli_guardrail import REFUSAL_TEXT, verify_draft_answer
from app.reasoning.state import AgentState, VerificationFailure


def run_verify_node(
    state: AgentState,
    *,
    evidence_result: AgentEvidenceBuildResult | None = None,
) -> AgentState:
    if state.exhausted_reasoning_budget:
        state.add_open_issue("Reasoning budget exhausted before verify step.")
        return state

    state.advance_step("verify")
    evidence_items = evidence_result.pack.all_evidence if evidence_result is not None else state.retrieved_evidence

    if not evidence_items:
        state.add_verification_failure(
            VerificationFailure(
                claim_text=state.draft_answer or "No draft answer",
                reason="No retrieved evidence was available to verify the answer.",
                severity="error",
                replacement_text=REFUSAL_TEXT,
            )
        )
        state.draft_answer = REFUSAL_TEXT
        return state

    if not state.draft_answer:
        state.add_verification_failure(
            VerificationFailure(
                claim_text="No draft answer",
                reason="Reasoning did not produce a draft answer.",
                severity="error",
                replacement_text=REFUSAL_TEXT,
            )
        )
        state.draft_answer = REFUSAL_TEXT
        return state

    verification = verify_draft_answer(
        state.draft_answer,
        evidence_items=evidence_items,
        query_type=state.query_type,
        missing_coverage=evidence_result.missing_coverage if evidence_result is not None else [],
    )
    for failure in verification.failures:
        state.add_verification_failure(failure)

    decision = apply_answer_policy(state.draft_answer, verification)
    state.trace_metadata["guardrail_backend"] = verification.backend
    state.trace_metadata["guardrail_removed_claims"] = decision.removed_claims

    if verification.has_errors:
        state.add_reasoning_note("Verification blocked unsupported factual claims from the final answer.")
    else:
        state.add_reasoning_note("Verification completed without unsupported factual claims.")

    state.draft_answer = decision.final_draft
    if decision.refused:
        state.draft_answer = REFUSAL_TEXT
    else:
        if decision.appended_notice and decision.appended_notice not in state.reasoning_summary:
            state.add_reasoning_note("Verification removed unsupported claims while preserving supported portions.")

    return state
