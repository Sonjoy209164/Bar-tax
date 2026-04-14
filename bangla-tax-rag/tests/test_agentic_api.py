import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import AgenticRuntimeStatus, CitationPayload, QueryResponse, TraceRecord
from app.domain import QueryType


class _FakeRuntime:
    def status(self) -> AgenticRuntimeStatus:
        return AgenticRuntimeStatus(
            ready=True,
            loaded_documents=["income-tax-act-2023"],
            node_count=10,
            link_count=12,
            retrieval_chunk_count=5,
            reasoning_chunk_count=2,
            vector_record_count=5,
            vector_backend="local",
            vector_store_path="data/agentic_store/local_vectors.jsonl",
        )

    def query(self, request):  # type: ignore[no-untyped-def]
        return QueryResponse(
            answer="Under the retrieved definition, Commissioner means Commissioner of Taxes.",
            citations=[
                CitationPayload(
                    node_id="income-tax-act-2023:section:2",
                    relation="direct",
                    section="2",
                    label="Section 2",
                )
            ],
            reasoning_summary=["Proceed through planning and retrieval."],
            missing_facts=[],
            confidence=0.9,
            trace_id="trace-123",
            verification_failures=[],
            query_type=QueryType.DEFINITION,
            execution_path="fast_path",
        )

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        if trace_id != "trace-123":
            return None
        return TraceRecord(
            trace_id=trace_id,
            state={"trace_id": trace_id, "question": "What is the definition of Commissioner?"},
        )


@pytest.mark.anyio
async def test_agentic_status_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes_agentic

    monkeypatch.setattr(routes_agentic, "get_agentic_runtime", lambda: _FakeRuntime())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/agentic/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["vector_backend"] == "local"


@pytest.mark.anyio
async def test_agentic_query_and_trace_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes_agentic

    monkeypatch.setattr(routes_agentic, "get_agentic_runtime", lambda: _FakeRuntime())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        query_response = await client.post(
            "/agentic/query",
            json={"question": "What is the definition of Commissioner?"},
        )
        trace_response = await client.get("/trace/trace-123")

    assert query_response.status_code == 200
    assert query_response.json()["trace_id"] == "trace-123"
    assert trace_response.status_code == 200
    assert trace_response.json()["state"]["question"] == "What is the definition of Commissioner?"
