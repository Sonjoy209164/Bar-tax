import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _configure_api_key(monkeypatch: pytest.MonkeyPatch, api_key: str = "test-api-key") -> str:
    from app.core.settings import get_settings

    monkeypatch.setenv("API_ACCESS_KEY", api_key)
    get_settings.cache_clear()
    return api_key


def _configure_rotated_api_keys(
    monkeypatch: pytest.MonkeyPatch,
    *,
    primary_key: str = "primary-key",
    rotated_keys: str = "legacy-key,next-key",
) -> tuple[str, str, str]:
    from app.core.settings import get_settings

    monkeypatch.setenv("API_ACCESS_KEY", primary_key)
    monkeypatch.setenv("API_ACCESS_KEYS", rotated_keys)
    get_settings.cache_clear()
    legacy_key, next_key = [value.strip() for value in rotated_keys.split(",")]
    return primary_key, legacy_key, next_key


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
async def test_inventory_policy_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/inventory/policy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "inventory-contract-v1"
    assert any(family["family"] == "exact_lookup" for family in payload["supported_question_families"])
    assert any(family["family"] == "planning_agentic_workflow" for family in payload["supported_question_families"])
    assert any(trigger["trigger_id"] == "hard_constraint_violation" for trigger in payload["hard_abstain_triggers"])
    assert "agentic-restock" in payload["canonical_eval_case_ids"]


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
async def test_protected_routes_accept_rotated_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import get_settings

    primary_key, legacy_key, next_key = _configure_rotated_api_keys(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        legacy_response = await client.get("/config", headers={"X-API-Key": legacy_key})
        primary_response = await client.get("/config", headers={"X-API-Key": primary_key})
        next_response = await client.get("/config", headers={"X-API-Key": next_key})

    assert legacy_response.status_code == 200
    assert primary_response.status_code == 200
    assert next_response.status_code == 200

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_protected_routes_rate_limit_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import get_settings

    api_key = _configure_api_key(monkeypatch)
    monkeypatch.setenv("API_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("API_RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_response = await client.get("/config", headers={"X-API-Key": api_key})
        second_response = await client.get("/config", headers={"X-API-Key": api_key})
        third_response = await client.get("/config", headers={"X-API-Key": api_key})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 429
    assert third_response.json()["detail"]["error"] == "rate_limited"
    assert third_response.json()["detail"]["retry_after_seconds"] >= 1

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
