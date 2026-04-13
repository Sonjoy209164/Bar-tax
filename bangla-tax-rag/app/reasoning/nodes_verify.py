from __future__ import annotations

import re

from app.reasoning.evidence_builder import AgentEvidenceBuildResult
from app.reasoning.state import AgentState, VerificationFailure

NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d+(?:\.\d+)?(?:\s*%| percent)?\b", re.IGNORECASE)
SECTION_CLAIM_PATTERN = re.compile(r"\bsection\s+(\d+[A-Za-z]?)\b", re.IGNORECASE)


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
                replacement_text="Information not found in retrieved evidence.",
            )
        )
        state.draft_answer = "Information not found in retrieved evidence."
        return state

    if not state.draft_answer:
        state.add_verification_failure(
            VerificationFailure(
                claim_text="No draft answer",
                reason="Reasoning did not produce a draft answer.",
                severity="error",
                replacement_text="Information not found in retrieved evidence.",
            )
        )
        state.draft_answer = "Information not found in retrieved evidence."
        return state

    evidence_text = " ".join(item.source_text.lower() for item in evidence_items)
    evidence_sections = {item.citation.section_number for item in evidence_items if item.citation.section_number}

    for numeric_claim in NUMERIC_CLAIM_PATTERN.findall(state.draft_answer):
        if numeric_claim.lower() not in evidence_text:
            state.add_verification_failure(
                VerificationFailure(
                    claim_text=numeric_claim,
                    reason=f"Numeric claim {numeric_claim!r} does not appear in retrieved evidence.",
                    severity="error",
                    evidence_ids=[item.evidence_id for item in evidence_items],
                    replacement_text="Information not found in retrieved evidence.",
                )
            )

    for section_number in SECTION_CLAIM_PATTERN.findall(state.draft_answer):
        if section_number not in evidence_sections:
            state.add_verification_failure(
                VerificationFailure(
                    claim_text=f"Section {section_number}",
                    reason=f"Section {section_number} is not supported by the retrieved citations.",
                    severity="warning",
                    evidence_ids=[item.evidence_id for item in evidence_items],
                )
            )

    if evidence_result is not None and evidence_result.missing_coverage:
        for issue in evidence_result.missing_coverage:
            state.add_verification_failure(
                VerificationFailure(
                    claim_text=issue,
                    reason="Evidence coverage is incomplete for this reasoning path.",
                    severity="warning",
                    evidence_ids=[item.evidence_id for item in evidence_items],
                )
            )

    if state.has_verification_errors:
        state.add_reasoning_note("Verification blocked unsupported factual claims from the final answer.")
        state.draft_answer = "Information not found in retrieved evidence."
    else:
        state.add_reasoning_note("Verification completed without unsupported numeric or section claims.")

    return state
