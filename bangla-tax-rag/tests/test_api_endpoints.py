import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.anyio
async def test_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_config_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/config")

    assert response.status_code == 200
    config = response.json()
    assert "generator_api_key" not in config
    assert "sparse_index_dir" in config


@pytest.mark.anyio
async def test_invalid_query_retrieval_mode() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/query",
            json={"question_text": "করহার কী?", "retrieval_mode": "invalid-mode"},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_query_with_mocked_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes_query
    from app.core.schemas import QueryAPIResponse, QuerySignals, RetrievalHit

    def fake_run_query_pipeline(request):  # type: ignore[no-untyped-def]
        return QueryAPIResponse(
            status="success",
            retrieval_mode="hybrid",
            analyzed_query=QuerySignals(
                original_query=request.question_text,
                normalized_query=request.question_text,
                query_type="general",
                query_intent="general",
            ),
            final_hits=[
                RetrievalHit(
                    chunk_id="chunk-1",
                    doc_id="doc-1",
                    doc_title="Test Document",
                    page_no=1,
                    section_id="3",
                    subsection_id=None,
                    chunk_type="text",
                    authority_level="national",
                    tax_year="2025-2026",
                    original_text="করহার ১০ শতাংশ",
                    normalized_text="করহার 10 শতাংশ",
                    heading_path=["ধারা 3"],
                    content="করহার ১০ শতাংশ",
                    score=1.2,
                    intermediate_scores={},
                )
            ],
            conflict_notes=[],
            answer="করহার ১০ শতাংশ। [C1]",
            citations=[],
            abstained=False,
        )

    monkeypatch.setattr(routes_query, "_run_query_pipeline", fake_run_query_pipeline)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/query",
            json={"question_text": "করহার কী?", "retrieval_mode": "hybrid"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "করহার ১০ শতাংশ। [C1]"
    assert payload["retrieval_mode"] == "hybrid"


@pytest.mark.anyio
async def test_ingest_request_validation() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ingest", json={"doc_id": "sample-doc"})

    assert response.status_code == 422


@pytest.mark.anyio
async def test_build_index_request_validation() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/build-index",
            json={
                "chunk_jsonl_path": "data/processed/missing.jsonl",
                "build_sparse": False,
                "build_dense": False,
            },
        )

    assert response.status_code == 422
