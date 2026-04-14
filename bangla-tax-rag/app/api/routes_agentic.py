from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services import (
    AgenticRuntimeStatus,
    EvaluationCase,
    EvaluationSummary,
    QueryRequest as AgenticQueryRequest,
    QueryResponse as AgenticQueryResponse,
    TraceRecord,
    get_agentic_runtime,
)

router = APIRouter(tags=["agentic"])


class AgenticIngestRequest(BaseModel):
    source_path: str
    document_id: str | None = None
    act_title: str | None = None


class AgenticIngestResponse(BaseModel):
    status: str
    document_id: str
    act_title: str
    parser_provider: str
    graph_path: str
    bm25_index_dir: str
    retrieval_chunk_count: int
    reasoning_chunk_count: int
    vector_record_count: int


class AgenticEvaluateRequest(BaseModel):
    cases: list[EvaluationCase] = Field(default_factory=list)


@router.get("/agentic/status", response_model=AgenticRuntimeStatus)
async def get_agentic_status() -> AgenticRuntimeStatus:
    runtime = get_agentic_runtime()
    return runtime.status()


@router.post("/agentic/ingest", response_model=AgenticIngestResponse)
async def ingest_agentic_document(request: AgenticIngestRequest) -> AgenticIngestResponse:
    runtime = get_agentic_runtime()
    source_path = Path(request.source_path)
    if not source_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_file", "message": f"File not found: {source_path}"},
        )
    try:
        result = runtime.ingest(
            request.source_path,
            document_id=request.document_id,
            act_title=request.act_title,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "agentic_ingest_failed", "message": str(exc)},
        ) from exc
    return AgenticIngestResponse(
        status="success",
        document_id=result.document_id,
        act_title=result.act_title,
        parser_provider=result.parser_provider,
        graph_path=result.document_store.graph_path,
        bm25_index_dir=result.bm25_index_dir,
        retrieval_chunk_count=result.retrieval_chunk_count,
        reasoning_chunk_count=result.reasoning_chunk_count,
        vector_record_count=result.vector_record_count,
    )


@router.post("/agentic/query", response_model=AgenticQueryResponse)
async def query_agentic_runtime(request: AgenticQueryRequest) -> AgenticQueryResponse:
    runtime = get_agentic_runtime()
    try:
        return runtime.query(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "agentic_runtime_not_ready", "message": str(exc)},
        ) from exc


@router.post("/agentic/evaluate", response_model=EvaluationSummary)
async def evaluate_agentic_runtime(request: AgenticEvaluateRequest) -> EvaluationSummary:
    runtime = get_agentic_runtime()
    try:
        return runtime.evaluate(request.cases)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "agentic_runtime_not_ready", "message": str(exc)},
        ) from exc


@router.get("/trace/{trace_id}", response_model=TraceRecord)
async def read_trace(trace_id: str) -> TraceRecord:
    runtime = get_agentic_runtime()
    trace = runtime.get_trace(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "trace_not_found", "message": f"Trace {trace_id} was not found."},
        )
    return trace
