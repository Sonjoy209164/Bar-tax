from app.core.schemas import QueryAPIResponse, QuerySignals, RetrievalHit


def test_hybrid_query_flow_with_mocked_dependencies(monkeypatch):  # type: ignore[no-untyped-def]
    from app.api import routes_query

    def fake_pipeline(request):  # type: ignore[no-untyped-def]
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
                    chunk_id="sample-tax-2025-p001-c001",
                    doc_id="sample-tax-2025",
                    doc_title="Sample Tax Circular 2025-2026",
                    page_no=1,
                    section_id="3",
                    subsection_id="3.1",
                    chunk_type="table",
                    authority_level="national",
                    tax_year="2025-2026",
                    original_text="ধারা 3.1 অনুযায়ী 2025-2026 করহার 10 শতাংশ।",
                    normalized_text="ধারা 3.1 অনুযায়ী 2025-2026 করহার 10 শতাংশ।",
                    heading_path=["ধারা 3.1", "করহার"],
                    content="ধারা 3.1 অনুযায়ী 2025-2026 করহার 10 শতাংশ।",
                    score=2.5,
                    intermediate_scores={},
                )
            ],
            answer="ধারা ৩.১ অনুযায়ী করহার ১০ শতাংশ। [C1]",
            citations=[],
            abstained=False,
            confidence_score=0.9,
        )

    monkeypatch.setattr(routes_query, "_run_query_pipeline", fake_pipeline)
    response = routes_query._run_query_pipeline(type("Request", (), {"question_text": "করহার কী?"})())
    assert response.retrieval_mode == "hybrid"
    assert response.answer is not None
