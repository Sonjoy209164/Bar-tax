from __future__ import annotations

from app.reasoning.state import AgentState
from app.retrieval import QueryTransformer


def run_planner_node(
    state: AgentState,
    *,
    query_transformer: QueryTransformer,
) -> AgentState:
    if state.exhausted_reasoning_budget:
        state.add_open_issue("Reasoning budget exhausted before planner step.")
        return state

    state.advance_step("planner")
    plan = query_transformer.transform(state.question, query_type=state.query_type)

    state.normalized_question = plan.normalized_question
    state.query_type = plan.query_type
    state.execution_path = plan.execution_path
    state.planned_steps = plan.steps
    state.trace_metadata["query_plan_focus_terms"] = plan.focus_terms
    state.trace_metadata["query_plan_sections"] = plan.section_references
    state.trace_metadata["query_plan_expansions"] = plan.legal_expansions

    for note in plan.notes:
        state.add_reasoning_note(note)
    state.add_reasoning_note(f"Planned {len(plan.steps)} focused retrieval steps.")
    return state
