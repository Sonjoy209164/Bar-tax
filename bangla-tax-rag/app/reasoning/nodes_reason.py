from __future__ import annotations

import re

from app.domain import QueryType
from app.reasoning.evidence_builder import AgentEvidenceBuildResult
from app.reasoning.state import AgentState

NUMERIC_FACT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?(?:\s*%| percent)?\b")


def run_reason_node(
    state: AgentState,
    *,
    evidence_result: AgentEvidenceBuildResult | None = None,
) -> AgentState:
    if state.exhausted_reasoning_budget:
        state.add_open_issue("Reasoning budget exhausted before reason step.")
        return state

    state.advance_step("reason")
    pack = evidence_result.pack if evidence_result is not None else None
    evidence_items = pack.all_evidence if pack is not None else state.retrieved_evidence

    if not evidence_items:
        state.add_open_issue("No grounded evidence was available for reasoning.")
        state.draft_answer = "Information not found in retrieved evidence."
        state.needs_more_retrieval = False
        return state

    for item in evidence_items:
        label = item.citation.citability_label or item.node_id
        if item.citation.relation.value in {"direct", "governing_rule", "parent_context"}:
            state.add_rule_found(label)
        if str(item.metadata.get("node_type")) in {"proviso", "explanation"}:
            state.add_exception_found(label)
        numbers = NUMERIC_FACT_PATTERN.findall(item.source_text)
        if numbers:
            state.add_fact_found(f"{label} includes numeric terms: {', '.join(numbers[:3])}.")

    for missing in _infer_missing_facts(state):
        state.add_missing_fact(missing)

    state.draft_answer = _build_draft_answer(state, evidence_items)
    if pack is not None and pack.missing_coverage:
        for issue in pack.missing_coverage:
            state.add_open_issue(issue)
    state.needs_more_retrieval = bool(
        pack is not None
        and pack.missing_coverage
        and state.should_enter_agent_loop
        and len(state.retrieval_attempts) < 2
        and not state.missing_facts
    )
    state.add_reasoning_note("Draft answer composed from the selected evidence pack.")
    return state


def _build_draft_answer(state: AgentState, evidence_items: list) -> str:
    lead = _lead_sentence(evidence_items[0].source_text)
    if state.query_type is QueryType.DEFINITION:
        return f"Under the retrieved definition, {lead}"
    if state.query_type is QueryType.SECTION_LOOKUP:
        return f"The retrieved section evidence centers on {lead}"
    if state.query_type in {QueryType.TABLE_LOOKUP, QueryType.RATE_LOOKUP, QueryType.AMOUNT_LOOKUP}:
        return f"The retrieved rule and table evidence indicate: {lead}"
    if state.query_type in {QueryType.COMPARISON, QueryType.CROSS_SECTION_REASONING}:
        section_labels = ", ".join(state.rules_found[:2]) if state.rules_found else "multiple linked provisions"
        return f"The retrieved evidence spans {section_labels}. The leading provision states: {lead}"
    if state.query_type in {QueryType.SCENARIO_REASONING, QueryType.ELIGIBILITY}:
        answer = f"Based on the retrieved provisions, {lead}"
        if state.exceptions_found:
            answer += f" Relevant exception or explanation context appears in {state.exceptions_found[0]}."
        if state.missing_facts:
            answer += f" A full conclusion still depends on: {state.missing_facts[0]}."
        return answer
    return f"Based on the retrieved evidence, {lead}"


def _lead_sentence(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1 and re.match(r"^\d+[A-Za-z]?(?:\.\d+)?\.\s+.+$", lines[0]):
        lines = lines[1:]
    normalized = " ".join(lines).strip() or text.strip()
    normalized = re.sub(r"^\((\d+[A-Za-z]?)\)\s*", "", normalized)
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?;:])\s+", normalized) if sentence.strip()]
    for sentence in sentences:
        if re.fullmatch(r"\d+[A-Za-z]?\.", sentence):
            continue
        if not sentence.endswith("."):
            sentence += "."
        return sentence
    fallback = normalized or text.strip()
    if fallback and not fallback.endswith("."):
        fallback += "."
    return fallback


def _infer_missing_facts(state: AgentState) -> list[str]:
    question = (state.normalized_question or state.question).lower()
    missing: list[str] = []
    if state.query_type is QueryType.ELIGIBILITY:
        if not any(token in question for token in ("income", "annual", "salary", "wage", "taka", "amount")):
            missing.append("Annual income or taxable amount is not stated.")
        if "tax year" not in question and "assessment year" not in question:
            missing.append("Relevant tax year is not stated.")
    if state.query_type is QueryType.SCENARIO_REASONING:
        if not any(token in question for token in ("director", "employee", "company", "assessee", "worker", "labour")):
            missing.append("The taxpayer role or legal status is not fully specified.")
    return missing
