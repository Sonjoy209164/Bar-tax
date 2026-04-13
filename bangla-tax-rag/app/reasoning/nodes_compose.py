from __future__ import annotations

from app.reasoning.state import AgentState


def run_compose_node(state: AgentState) -> AgentState:
    if not state.exhausted_reasoning_budget:
        state.advance_step("compose")

    conclusion = state.draft_answer or "Information not found in retrieved evidence."
    parts = [conclusion]

    if state.rules_found:
        parts.append("Legal basis: " + "; ".join(state.rules_found[:3]))
    if state.reasoning_summary:
        parts.append("Reasoning: " + " ".join(state.reasoning_summary[:3]))
    if state.missing_facts:
        parts.append("Missing facts: " + "; ".join(state.missing_facts[:3]))
    if state.citations:
        parts.append(
            "Citations: "
            + "; ".join(
                citation.citability_label or f"Section {citation.section_number}" if citation.section_number else citation.node_id
                for citation in state.citations[:4]
            )
        )
    if state.verification_failures:
        parts.append("Verification: unsupported or incomplete claims were withheld from the final answer.")

    state.final_answer = "\n\n".join(part for part in parts if part.strip())
    state.confidence = _derive_confidence(state)
    return state


def _derive_confidence(state: AgentState) -> float:
    score = 0.35
    if state.retrieved_evidence:
        score += 0.3
    if state.rules_found:
        score += 0.15
    if state.citations:
        score += 0.1
    if state.missing_facts:
        score -= 0.1
    if state.has_verification_errors:
        score -= 0.25
    return max(0.0, min(1.0, round(score, 2)))
