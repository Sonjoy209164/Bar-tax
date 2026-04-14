from __future__ import annotations

from importlib import import_module

_SYMBOL_MODULES = {
    "LANGGRAPH_AVAILABLE": "app.reasoning.agent_graph",
    "AgentState": "app.reasoning.state",
    "AgentEvidenceBuildResult": "app.reasoning.evidence_builder",
    "AgentEvidenceBuilder": "app.reasoning.evidence_builder",
    "AgenticReasoningGraph": "app.reasoning.agent_graph",
    "AnswerPolicyDecision": "app.reasoning.answer_policy",
    "DeterministicNliGuardrail": "app.reasoning.nli_guardrail",
    "GuardrailClaimResult": "app.reasoning.nli_guardrail",
    "GuardrailVerificationResult": "app.reasoning.nli_guardrail",
    "GuardrailedAnswerPolicy": "app.reasoning.answer_policy",
    "QueryPlanStep": "app.reasoning.state",
    "REFUSAL_TEXT": "app.reasoning.nli_guardrail",
    "ReasoningGraphConfig": "app.reasoning.agent_graph",
    "ReasoningGraphDependencies": "app.reasoning.agent_graph",
    "RetrievalAttempt": "app.reasoning.state",
    "RouterDecision": "app.reasoning.nodes_router",
    "VerificationFailure": "app.reasoning.state",
    "apply_answer_policy": "app.reasoning.answer_policy",
    "apply_evidence_build_result": "app.reasoning.evidence_builder",
    "build_agent_evidence": "app.reasoning.evidence_builder",
    "build_agent_graph": "app.reasoning.agent_graph",
    "route_agent_state": "app.reasoning.nodes_router",
    "run_compose_node": "app.reasoning.nodes_compose",
    "run_planner_node": "app.reasoning.nodes_planner",
    "run_reason_node": "app.reasoning.nodes_reason",
    "run_retrieve_node": "app.reasoning.nodes_retrieve",
    "run_router_node": "app.reasoning.nodes_router",
    "run_verify_node": "app.reasoning.nodes_verify",
    "verify_draft_answer": "app.reasoning.nli_guardrail",
}

__all__ = sorted(_SYMBOL_MODULES)


def __getattr__(name: str):
    module_name = _SYMBOL_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value
