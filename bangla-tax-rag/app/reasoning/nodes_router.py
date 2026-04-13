from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.domain import QueryExecutionPath
from app.reasoning.state import AgentState


class RouterDecision(BaseModel):
    next_node: Literal["planner", "compose"]
    reason: str


def route_agent_state(state: AgentState) -> RouterDecision:
    if state.execution_path is QueryExecutionPath.CLARIFICATION:
        return RouterDecision(
            next_node="compose",
            reason="Question is unsupported or underspecified and should move to clarification/refusal.",
        )
    return RouterDecision(next_node="planner", reason="Proceed through planning and retrieval.")


def run_router_node(state: AgentState) -> AgentState:
    if state.exhausted_reasoning_budget:
        state.add_open_issue("Reasoning budget exhausted before router step.")
        return state

    state.advance_step("router")
    decision = route_agent_state(state)
    state.trace_metadata["router_next_node"] = decision.next_node
    state.trace_metadata["router_reason"] = decision.reason
    state.add_reasoning_note(decision.reason)

    if state.execution_path is QueryExecutionPath.CLARIFICATION:
        state.add_missing_fact("The question needs clarification or supporting facts before a grounded answer is possible.")
        if not state.draft_answer:
            state.draft_answer = "Information not found in retrieved evidence."

    return state
