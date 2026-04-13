from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.domain import QueryExecutionPath, QueryType, canonicalize_query_type, infer_execution_path
from app.reasoning.evidence_builder import AgentEvidenceBuilder
from app.reasoning.nodes_compose import run_compose_node
from app.reasoning.nodes_planner import run_planner_node
from app.reasoning.nodes_reason import run_reason_node
from app.reasoning.nodes_retrieve import run_retrieve_node
from app.reasoning.nodes_router import route_agent_state, run_router_node
from app.reasoning.nodes_verify import run_verify_node
from app.reasoning.state import AgentState
from app.retrieval import HybridRetriever, QueryTransformer

try:  # pragma: no cover - optional dependency surface
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover - intentionally broad to avoid hard dependency coupling
    END = None
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


class ReasoningGraphConfig(BaseModel):
    top_k: int = Field(default=5, ge=1, le=20)
    max_retrieval_loops: int = Field(default=2, ge=1, le=4)
    prefer_langgraph_backend: bool = True


@dataclass
class ReasoningGraphDependencies:
    hybrid_retriever: HybridRetriever
    query_transformer: QueryTransformer | None = None
    evidence_builder: AgentEvidenceBuilder | None = None


class AgenticReasoningGraph:
    def __init__(
        self,
        *,
        dependencies: ReasoningGraphDependencies,
        config: ReasoningGraphConfig | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.config = config or ReasoningGraphConfig()
        self.query_transformer = dependencies.query_transformer or QueryTransformer()
        self.evidence_builder = dependencies.evidence_builder or AgentEvidenceBuilder()

    @property
    def backend_name(self) -> str:
        if self.config.prefer_langgraph_backend and LANGGRAPH_AVAILABLE:
            return "langgraph"
        return "python_fallback"

    def invoke(
        self,
        state_or_question: AgentState | str,
        *,
        query_type: str | QueryType | None = None,
        max_reasoning_steps: int | None = None,
    ) -> AgentState:
        state = _coerce_state(
            state_or_question,
            query_type=query_type,
            max_reasoning_steps=max_reasoning_steps,
        )
        state.trace_metadata["reasoning_backend"] = self.backend_name
        if self.backend_name == "langgraph":
            compiled = self.compile_langgraph()
            if compiled is not None:
                return compiled.invoke(state)
        return self._run_python_fallback(state)

    def compile_langgraph(self):  # pragma: no cover - optional dependency path
        if not LANGGRAPH_AVAILABLE or StateGraph is None or END is None:
            return None

        workflow = StateGraph(AgentState)
        workflow.add_node("router", lambda state: run_router_node(state))
        workflow.add_node("planner", lambda state: run_planner_node(state, query_transformer=self.query_transformer))
        workflow.add_node(
            "retrieve",
            lambda state: run_retrieve_node(
                state,
                hybrid_retriever=self.dependencies.hybrid_retriever,
                evidence_builder=self.evidence_builder,
                top_k=self.config.top_k,
            )[0],
        )
        workflow.add_node("reason", lambda state: run_reason_node(state))
        workflow.add_node("verify", lambda state: run_verify_node(state))
        workflow.add_node("compose", lambda state: run_compose_node(state))

        workflow.set_entry_point("router")
        workflow.add_conditional_edges(
            "router",
            lambda state: route_agent_state(state).next_node,
            {"planner": "planner", "compose": "compose"},
        )
        workflow.add_edge("planner", "retrieve")
        workflow.add_edge("retrieve", "reason")
        workflow.add_conditional_edges(
            "reason",
            lambda state: "retrieve" if _should_retry_retrieval(state, max_loops=self.config.max_retrieval_loops) else "verify",
            {"retrieve": "retrieve", "verify": "verify"},
        )
        workflow.add_edge("verify", "compose")
        workflow.add_edge("compose", END)
        return workflow.compile()

    def _run_python_fallback(self, state: AgentState) -> AgentState:
        state = run_router_node(state)
        if route_agent_state(state).next_node == "compose":
            return run_compose_node(state)

        state = run_planner_node(state, query_transformer=self.query_transformer)
        evidence_result = None
        retrieval_loops = 0
        while True:
            state, evidence_result = run_retrieve_node(
                state,
                hybrid_retriever=self.dependencies.hybrid_retriever,
                evidence_builder=self.evidence_builder,
                top_k=self.config.top_k,
            )
            state = run_reason_node(state, evidence_result=evidence_result)
            retrieval_loops += 1
            if not _should_retry_retrieval(state, max_loops=self.config.max_retrieval_loops, loops_used=retrieval_loops):
                break

        state = run_verify_node(state, evidence_result=evidence_result)
        state = run_compose_node(state)
        return state


def build_agent_graph(
    *,
    dependencies: ReasoningGraphDependencies,
    config: ReasoningGraphConfig | None = None,
) -> AgenticReasoningGraph:
    return AgenticReasoningGraph(dependencies=dependencies, config=config)


def _coerce_state(
    state_or_question: AgentState | str,
    *,
    query_type: str | QueryType | None,
    max_reasoning_steps: int | None,
) -> AgentState:
    if isinstance(state_or_question, AgentState):
        if query_type is not None:
            canonical_type = canonicalize_query_type(query_type)
            state_or_question.query_type = canonical_type
            state_or_question.execution_path = infer_execution_path(canonical_type)
        if max_reasoning_steps is not None:
            state_or_question.max_reasoning_steps = max_reasoning_steps
        return state_or_question

    canonical_type = canonicalize_query_type(query_type)
    execution_path = infer_execution_path(canonical_type)
    return AgentState(
        question=state_or_question,
        query_type=canonical_type,
        execution_path=execution_path,
        max_reasoning_steps=max_reasoning_steps or 6,
    )


def _should_retry_retrieval(
    state: AgentState,
    *,
    max_loops: int,
    loops_used: int | None = None,
) -> bool:
    if not state.needs_more_retrieval:
        return False
    if state.exhausted_reasoning_budget:
        return False
    if loops_used is not None and loops_used >= max_loops:
        return False
    if len(state.retrieval_attempts) >= max_loops:
        return False
    return True
