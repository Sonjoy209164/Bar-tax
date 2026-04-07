from app.core.schemas import RetrievalHit
from app.retrieval.hybrid import (
    build_evidence_pack,
    reciprocal_rank_fusion,
    run_hybrid_retrieval,
)


def _hit(
    *,
    chunk_id: str,
    score: float,
    doc_id: str = "doc",
    doc_title: str = "Doc Title",
    page_no: int = 1,
    section_id: str | None = None,
    subsection_id: str | None = None,
    chunk_type: str = "text",
    authority_level: str = "national",
    tax_year: str | None = None,
    heading_path: list[str] | None = None,
    text: str = "sample text",
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_title=doc_title,
        page_no=page_no,
        section_id=section_id,
        subsection_id=subsection_id,
        chunk_type=chunk_type,
        authority_level=authority_level,
        tax_year=tax_year,
        original_text=text,
        normalized_text=text,
        heading_path=heading_path or [],
        content=text,
        score=score,
        intermediate_scores={},
    )


def test_reciprocal_rank_fusion_prefers_consensus_hits() -> None:
    sparse_hits = [_hit(chunk_id="a", score=5.0), _hit(chunk_id="b", score=4.0)]
    dense_hits = [_hit(chunk_id="b", score=3.5), _hit(chunk_id="a", score=3.0)]

    fused_hits = reciprocal_rank_fusion(sparse_hits=sparse_hits, dense_hits=dense_hits, rrf_k=10)

    assert {hit.chunk_id for hit in fused_hits[:2]} == {"a", "b"}
    assert "rrf_score" in fused_hits[0].intermediate_scores


def test_chunk_deduplication_drops_near_duplicate_text() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="করহার",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(chunk_id="a", score=3.0, text="করহার 10 শতাংশ কোম্পানির জন্য"),
        _hit(chunk_id="b", score=2.9, text="করহার 10 শতাংশ কোম্পানির জন্য"),
    ]

    final_hits, _, _, dropped_duplicates = build_evidence_pack(fused_hits, analyzed_query, final_top_k=5)

    assert len(final_hits) == 1
    assert dropped_duplicates == ["b"]


def test_authority_aware_preference_and_conflict_note_generation() -> None:
    low_authority_hit = _hit(
        chunk_id="local-1",
        score=2.0,
        section_id="3",
        authority_level="regional",
        tax_year="2025-2026",
        heading_path=["ধারা 3", "করহার"],
    )
    high_authority_hit = _hit(
        chunk_id="national-1",
        score=2.0,
        section_id="3",
        authority_level="national",
        tax_year="2024-2025",
        heading_path=["ধারা 3", "করহার"],
    )

    response = run_hybrid_retrieval(
        query="ধারা ৩ করহার",
        sparse_hits_override=[low_authority_hit],
        dense_hits_override=[high_authority_hit],
        final_top_k=2,
    )

    assert response.final_hits[0].authority_level == "national"
    assert response.conflict_notes


def test_tax_year_aware_ranking_prefers_exact_match() -> None:
    exact_year_hit = _hit(chunk_id="year-a", score=1.0, tax_year="2025-2026", section_id="3")
    other_year_hit = _hit(chunk_id="year-b", score=1.0, tax_year="2024-2025", section_id="3")

    response = run_hybrid_retrieval(
        query="২০২৫-২০২৬ ধারা ৩",
        sparse_hits_override=[other_year_hit],
        dense_hits_override=[exact_year_hit],
        final_top_k=2,
    )

    assert response.final_hits[0].chunk_id == "year-a"


def test_hybrid_retrieval_on_tiny_synthetic_corpus() -> None:
    sparse_hits = [
        _hit(
            chunk_id="c1",
            score=5.0,
            section_id="3",
            subsection_id="3.1",
            chunk_type="table",
            tax_year="2025-2026",
            heading_path=["ধারা 3.1", "করহার"],
            text="ধারা 3.1 অনুযায়ী করহার 10 শতাংশ",
        ),
        _hit(chunk_id="c2", score=3.0, text="অন্য সাধারণ বর্ণনা"),
    ]
    dense_hits = [
        _hit(
            chunk_id="c1",
            score=2.5,
            section_id="3",
            subsection_id="3.1",
            chunk_type="table",
            tax_year="2025-2026",
            heading_path=["ধারা 3.1", "করহার"],
            text="ধারা 3.1 অনুযায়ী করহার 10 শতাংশ",
        ),
        _hit(chunk_id="c3", score=2.0, chunk_type="example", text="উদাহরণ সহ ব্যাখ্যা"),
    ]

    response = run_hybrid_retrieval(
        query="২০২৫-২০২৬ ধারা ৩.১ অনুযায়ী করহার কী?",
        sparse_hits_override=sparse_hits,
        dense_hits_override=dense_hits,
        final_top_k=2,
        rrf_k=20,
    )

    assert response.final_hits
    assert response.final_hits[0].chunk_id == "c1"
    assert response.evidence_summary
