from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.core.utils import detect_query_type
from app.domain import QueryType, canonicalize_query_type, infer_execution_path
from app.reasoning import AgentState, AgenticReasoningGraph
from app.services.citation_service import CitationPayload, CitationService


class QueryServiceConfig(BaseModel):
    default_top_k: int = Field(default=5, ge=1, le=20)
    default_max_reasoning_steps: int = Field(default=6, ge=1, le=12)


class QueryRequest(BaseModel):
    question: str
    query_type: QueryType | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    max_reasoning_steps: int | None = Field(default=None, ge=1, le=12)

    @model_validator(mode="after")
    def normalize_request(self) -> "QueryRequest":
        self.query_type = canonicalize_query_type(self.query_type or detect_query_type(self.question))
        return self


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationPayload] = Field(default_factory=list)
    reasoning_summary: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    trace_id: str
    verification_failures: list[str] = Field(default_factory=list)
    query_type: QueryType
    execution_path: str


class QueryService:
    def __init__(
        self,
        *,
        reasoning_graph: AgenticReasoningGraph,
        citation_service: CitationService | None = None,
        config: QueryServiceConfig | None = None,
    ) -> None:
        self.reasoning_graph = reasoning_graph
        self.citation_service = citation_service or CitationService()
        self.config = config or QueryServiceConfig()

    def run(self, request: QueryRequest) -> QueryResponse:
        response, _ = self.run_with_state(request)
        return response

    def run_with_state(self, request: QueryRequest) -> tuple[QueryResponse, AgentState]:
        state = AgentState(
            question=request.question,
            query_type=request.query_type or QueryType.GENERAL,
            execution_path=infer_execution_path(request.query_type or QueryType.GENERAL),
            max_reasoning_steps=request.max_reasoning_steps or self.config.default_max_reasoning_steps,
        )
        final_state = self.reasoning_graph.invoke(
            state,
            query_type=request.query_type,
            max_reasoning_steps=request.max_reasoning_steps or self.config.default_max_reasoning_steps,
        )

        response = QueryResponse(
            answer=final_state.final_answer or final_state.draft_answer or "Information not found in retrieved evidence.",
            citations=self.citation_service.build_payloads(final_state.citations),
            reasoning_summary=list(final_state.reasoning_summary),
            missing_facts=list(final_state.missing_facts),
            confidence=final_state.confidence or 0.0,
            trace_id=final_state.trace_id,
            verification_failures=[failure.reason for failure in final_state.verification_failures],
            query_type=final_state.query_type,
            execution_path=final_state.execution_path.value,
        )
        return response, final_state
