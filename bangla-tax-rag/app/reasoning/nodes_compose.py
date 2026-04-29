from __future__ import annotations

from app.core.utils import detect_text_language
from app.reasoning.prompt_strategies import normalize_prompt_strategy
from app.reasoning.state import AgentState


def run_compose_node(state: AgentState) -> AgentState:
    if not state.exhausted_reasoning_budget:
        state.advance_step("compose")

    conclusion = state.draft_answer or "Information not found in retrieved evidence."
    parts = [conclusion]
    prompt_strategy = normalize_prompt_strategy(state.prompt_strategy)
    strategy_has_basis = prompt_strategy in {"one_shot", "few_shot"}
    evidence_only = prompt_strategy == "evidence_only"
    bangla_labels = detect_text_language(conclusion) == "bangla" or detect_text_language(state.question) == "bangla"

    if state.rules_found and not strategy_has_basis:
        parts.append(_label("আইনি ভিত্তি", "Legal basis", bangla_labels) + ": " + "; ".join(state.rules_found[:3]))
    if state.reasoning_summary and not evidence_only:
        parts.append(_label("যুক্তির সারাংশ", "Reasoning", bangla_labels) + ": " + " ".join(state.reasoning_summary[:3]))
    if state.missing_facts:
        parts.append(_label("অপূর্ণ তথ্য", "Missing facts", bangla_labels) + ": " + "; ".join(state.missing_facts[:3]))
    if state.citations:
        parts.append(
            _label("উৎস", "Citations", bangla_labels)
            + ": "
            + "; ".join(
                citation.citability_label or f"Section {citation.section_number}" if citation.section_number else citation.node_id
                for citation in state.citations[:4]
            )
        )
    if state.has_verification_errors:
        parts.append(
            _label("যাচাই", "Verification", bangla_labels)
            + ": unsupported or incomplete claims were withheld from the final answer."
        )
    elif state.verification_failures:
        parts.append(_label("যাচাই", "Coverage note", bangla_labels) + ": some linked context was not retrieved.")

    state.final_answer = "\n\n".join(part for part in parts if part.strip())
    state.confidence = _derive_confidence(state)
    return state


def _label(bangla: str, english: str, use_bangla: bool) -> str:
    return bangla if use_bangla else english


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
