import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _configure_api_key(monkeypatch: pytest.MonkeyPatch, api_key: str = "test-api-key") -> str:
    from app.core.settings import get_settings

    monkeypatch.setenv("API_ACCESS_KEY", api_key)
    get_settings.cache_clear()
    return api_key


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
async def test_query_returns_abstention_when_no_exact_support(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes_query
    from app.core.schemas import QueryAPIResponse, QuerySignals

    def fake_run_query_pipeline(request):  # type: ignore[no-untyped-def]
        return QueryAPIResponse(
            status="success",
            retrieval_mode="hybrid",
            analyzed_query=QuerySignals(
                original_query=request.question_text,
                normalized_query="2025-2026 ধারা 3.1 অনুযায়ী করহার কী?",
                section_reference="3.1",
                section_id="3",
                subsection_id="3.1",
                query_type="rate_lookup",
                query_intent="rate_lookup",
            ),
            final_hits=[],
            conflict_notes=["No final evidence directly supports the requested section or subsection."],
            answer=None,
            citations=[],
            abstained=True,
            abstention_reason="No final evidence directly supports the requested section or subsection.",
            confidence_score=0.0,
        )

    monkeypatch.setattr(routes_query, "_run_query_pipeline", fake_run_query_pipeline)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/query",
            json={"question_text": "২০২৫-২০২৬ করবর্ষে ধারা ৩.১ অনুযায়ী করহার কী?", "retrieval_mode": "hybrid"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["final_hits"] == []
    assert payload["abstained"] is True


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


@pytest.mark.anyio
async def test_protected_routes_require_api_key_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import get_settings

    api_key = _configure_api_key(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        config_forbidden = await client.get("/config")
        query_forbidden = await client.post("/query", json={"question_text": "করহার কী?"})
        config_allowed = await client.get("/config", headers={"X-API-Key": api_key})

    assert config_forbidden.status_code == 403
    assert query_forbidden.status_code == 403
    assert config_allowed.status_code == 200

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_docs_and_openapi_stay_visible_when_api_key_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import get_settings

    _configure_api_key(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        docs_response = await client.get("/docs")
        openapi_response = await client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert "Swagger UI" in docs_response.text
    assert openapi_response.status_code == 200
    spec = openapi_response.json()
    assert "/inventory/status" in spec["paths"]
    assert spec["components"]["securitySchemes"]["ApiKeyAuth"]["name"] == "X-API-Key"
    assert spec["paths"]["/inventory/status"]["get"]["security"] == [{"ApiKeyAuth": []}]

    get_settings.cache_clear()
