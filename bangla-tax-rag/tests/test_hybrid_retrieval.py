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
        text="ধারা 3 অনুযায়ী করহার 10 শতাংশ",
    )
    high_authority_hit = _hit(
        chunk_id="national-1",
        score=2.0,
        section_id="3",
        authority_level="national",
        tax_year="2024-2025",
        heading_path=["ধারা 3", "করহার"],
        text="ধারা 3 অনুযায়ী করহার 12 শতাংশ",
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


def test_evidence_pack_abstains_when_subsection_query_has_no_direct_support() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="ধারা ৩.১ অনুযায়ী করহার কী?",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="wrong-1",
            score=5.0,
            section_id="3",
            subsection_id="3.1",
            chunk_type="table",
            text="ধারা 3.1 এর সংজ্ঞা",
            heading_path=["ধারা 3.1", "সংজ্ঞা"],
        ),
        _hit(
            chunk_id="wrong-2",
            score=4.5,
            section_id="2",
            subsection_id="2.3",
            chunk_type="table",
            text="2025-2026 করহার 10 শতাংশ",
            heading_path=["ধারা 2.3", "করহার"],
        ),
    ]

    final_hits, evidence_summary, conflict_notes, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
    )

    assert final_hits == []
    assert evidence_summary == "No evidence passed the final support checks."
    assert any("No final evidence directly supports" in note for note in conflict_notes)


def test_hybrid_mention_query_prefers_software_service_chunk() -> None:
    software_chunk = _hit(
        chunk_id="software-services",
        score=3.0,
        page_no=270,
        section_id="107",
        chunk_type="section",
        heading_path=["software test lab service", "website development and service"],
        text="software test lab service; website development and service; IT assistance and software maintenance service;",
    )
    unrelated_service_chunk = _hit(
        chunk_id="notice-service",
        score=3.0,
        page_no=224,
        section_id="335",
        chunk_type="section",
        heading_path=["335. Service of notice"],
        text="Service of notice may be sent to the specified electronic mail address of the person.",
    )
    software_chunk.intermediate_scores = {"sparse_score": 20.0, "dense_score": 0.5}
    unrelated_service_chunk.intermediate_scores = {"sparse_score": 8.0, "dense_score": 2.0}

    response = run_hybrid_retrieval(
        query="Is software service mentioned in the Act?",
        sparse_hits_override=[software_chunk],
        dense_hits_override=[unrelated_service_chunk],
        final_top_k=2,
    )

    assert response.analyzed_query.query_intent == "mention_lookup"
    assert response.final_hits
    assert response.final_hits[0].chunk_id == "software-services"


def test_evidence_pack_prefers_exact_section_heading_when_available() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="What are the income tax authorities under section 4?",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="exact-section",
            score=5.5,
            page_no=24,
            section_id="4",
            chunk_type="section",
            heading_path=["4. Income tax authorities.—For the purposes of this Act"],
            text="4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities.",
        ),
        _hit(
            chunk_id="incidental-reference",
            score=5.2,
            page_no=207,
            section_id="4",
            chunk_type="section",
            heading_path=["295. Appeal to the Appellate Division.—(1)"],
            text="Commissioner of Taxes from among the income tax authorities under section 4 to represent in the Alternative Dispute Resolution process.",
        ),
    ]

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
    )

    assert final_hits
    assert final_hits[0].chunk_id == "exact-section"


def test_definition_evidence_pack_prefers_exact_definition_hit() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="What is the definition of Commissioner?",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="definition-exact",
            score=5.4,
            page_no=6,
            section_id="2",
            chunk_type="section",
            heading_path=["2. Definitions"],
            text='(19) "Commissioner" means Commissioner of Taxes or Commissioner of Taxes (Large Assessee Unit).',
        ),
        _hit(
            chunk_id="definition-incidental",
            score=5.1,
            page_no=18,
            section_id="4",
            chunk_type="section",
            heading_path=["4. Income tax authorities"],
            text="The Commissioner of Taxes shall exercise the following powers under this Act.",
        ),
    ]

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=2,
    )

    assert final_hits
    assert final_hits[0].chunk_id == "definition-exact"
    assert all(hit.chunk_id != "definition-incidental" for hit in final_hits[1:])


def test_evidence_pack_expands_to_adjacent_clause_continuation_from_candidate_pool() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="How many classes of income tax authorities are listed under section 4?",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="section-4-anchor",
            score=5.8,
            page_no=24,
            section_id="4",
            chunk_type="section",
            heading_path=["4. Income tax authorities.—For the purposes of this Act"],
            text="4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities, namely:— (a) The National Board of Revenue; (b) Chief Commissioner of Taxes;",
        ),
    ]
    candidate_pool = [
        _hit(
            chunk_id="section-4-anchor",
            score=5.8,
            page_no=24,
            section_id="4",
            chunk_type="section",
            heading_path=["4. Income tax authorities.—For the purposes of this Act"],
            text="4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities, namely:— (a) The National Board of Revenue; (b) Chief Commissioner of Taxes;",
        ),
        _hit(
            chunk_id="section-4-continuation",
            score=0.0,
            page_no=25,
            section_id="4",
            chunk_type="section",
            heading_path=[],
            text="(c) Director General (Inspection); (d) Commissioner of Taxes (Appeals); (e) Commissioner of Taxes (Large Assessee Unit);",
        ),
    ]
    candidate_pool[1].intermediate_scores = {"from_corpus_pool": 1}

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
        candidate_pool=candidate_pool,
    )

    assert {hit.chunk_id for hit in final_hits} >= {"section-4-anchor", "section-4-continuation"}


def test_comparison_evidence_pack_keeps_complementary_hits() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="Compare the Tax Day for a company and for an assessee other than a company.",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="company-tax-day",
            score=5.0,
            page_no=8,
            section_id="2",
            chunk_type="section",
            heading_path=["2. Definitions"],
            text="(65)(b) in the case of a company, the 15th day of the seventh month following the end of the income year or 15 September, whichever is earlier;",
        ),
        _hit(
            chunk_id="other-tax-day",
            score=4.8,
            page_no=8,
            section_id="2",
            chunk_type="section",
            heading_path=["2. Definitions"],
            text="(65)(a) in the case of an assessee other than a company, the 30th day of November following the end of the income year;",
        ),
        _hit(
            chunk_id="irrelevant-date",
            score=4.7,
            page_no=30,
            section_id="17",
            chunk_type="section",
            heading_path=["17. Assessment year"],
            text="Assessment year means the period of twelve months commencing on the first day of July.",
        ),
    ]

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
    )

    assert {hit.chunk_id for hit in final_hits} >= {"company-tax-day", "other-tax-day"}
    assert all(hit.chunk_id != "irrelevant-date" for hit in final_hits)


def test_comparison_evidence_pack_prefers_self_contained_comparison_chunk() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="Compare the Tax Day for a company and for an assessee other than a company.",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="combined-tax-day",
            score=4.9,
            page_no=7,
            section_id="2",
            chunk_type="section",
            heading_path=["2. Definitions"],
            text=(
                "(23) Tax Day means (a) in the case of an assessee other than a company, the 30th day of November; "
                "(b) in the case of a company, the 15th day of the seventh month following the end of the income year."
            ),
        ),
        _hit(
            chunk_id="tax-day-penalty",
            score=4.8,
            page_no=121,
            section_id="173",
            chunk_type="section",
            heading_path=["173. Regarding payment of income tax and surcharge on or before the Tax Day"],
            text="The assessee would have paid if he had filed the return on the tax day.",
        ),
    ]

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
    )

    assert [hit.chunk_id for hit in final_hits] == ["combined-tax-day"]


def test_hybrid_evidence_pack_prefers_startup_duration_hit_for_duration_query() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="For how many successive assessment years can startup losses be carried forward?",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="startup-loss",
            score=4.8,
            page_no=286,
            section_id="2",
            chunk_type="section",
            heading_path=["STARTUP SANDBOX"],
            text="the amount of loss shall be carried forward and set off to the next 9 (nine) successive assessment years.",
        ),
        _hit(
            chunk_id="generic-assessment-year",
            score=4.7,
            page_no=234,
            section_id="3",
            chunk_type="table",
            heading_path=["4. Wealth tax table"],
            text="assets and liabilities or balance sheet furnished with the return filed for the assessment year 2024-25.",
        ),
    ]

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
    )

    assert final_hits
    assert final_hits[0].chunk_id == "startup-loss"
    assert all(hit.chunk_id != "incidental-reference" for hit in final_hits)


def test_evidence_pack_filters_out_wrong_topic_even_with_same_section_number() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="What are the income tax authorities under section 4?",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="authorities-section",
            score=5.5,
            page_no=24,
            section_id="4",
            chunk_type="section",
            heading_path=["4. Income tax authorities.—For the purposes of this Act"],
            text="There shall be the following classes of income tax authorities.",
        ),
        _hit(
            chunk_id="wrong-topic-section",
            score=5.3,
            page_no=265,
            section_id="4",
            chunk_type="appendix",
            heading_path=["4. Tax exemption of profits from refining or concentrating mineral"],
            text="The provisions of this paragraph shall apply to the assessment for the year next following the income year.",
        ),
    ]

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
    )

    assert final_hits
    assert final_hits[0].chunk_id == "authorities-section"
    assert all(hit.chunk_id != "wrong-topic-section" for hit in final_hits)


def test_evidence_pack_expands_same_heading_logical_unit_for_count_query() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="How many classes of income tax authorities are listed under section 4?",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="p024-c056",
            score=6.0,
            doc_id="income-tax-act-2023",
            doc_title="Income Tax Act 2023",
            page_no=24,
            section_id="4",
            chunk_type="section",
            heading_path=["TAX ADMINISTRATION", "4. Income tax authorities.—For the purposes of this Act, there shall be the"],
            text="(a) The National Board of Revenue; (b) Chief Commissioner of Taxes; (c) Director General (Inspection);",
        ),
        _hit(
            chunk_id="p024-c057",
            score=5.4,
            doc_id="income-tax-act-2023",
            doc_title="Income Tax Act 2023",
            page_no=24,
            section_id="16",
            chunk_type="section",
            heading_path=["TAX ADMINISTRATION", "4. Income tax authorities.—For the purposes of this Act, there shall be the"],
            text="(l) Tax Recovery Officers nominated by the Commissioner of Taxes among the Deputy Commissioners of Taxes within his jurisdiction;",
        ),
        _hit(
            chunk_id="p025-c058",
            score=5.0,
            doc_id="income-tax-act-2023",
            doc_title="Income Tax Act 2023",
            page_no=25,
            section_id="4",
            chunk_type="section",
            heading_path=["TAX ADMINISTRATION", "4. Income tax authorities.—For the purposes of this Act, there shall be the"],
            text="(m) Assistant Commissioners of Taxes; (n) Extra Assistant Commissioners of Taxes; and (o) Inspectors of Taxes.",
        ),
        _hit(
            chunk_id="irrelevant",
            score=5.8,
            doc_id="income-tax-act-2023",
            doc_title="Income Tax Act 2023",
            page_no=207,
            section_id="4",
            chunk_type="section",
            heading_path=["295. Appeal to the Appellate Division.—(1)"],
            text="Commissioner of Taxes from among the income tax authorities under section 4 may represent a party.",
        ),
    ]

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
    )

    assert [hit.chunk_id for hit in final_hits] == ["p024-c056", "p024-c057", "p025-c058"]


def test_evidence_pack_can_expand_from_candidate_pool_for_same_heading() -> None:
    analyzed_query = run_hybrid_retrieval(
        query="What are the income tax authorities under section 4?",
        sparse_hits_override=[],
        dense_hits_override=[],
    ).analyzed_query
    fused_hits = [
        _hit(
            chunk_id="p024-c056",
            score=6.0,
            doc_id="income-tax-act-2023",
            doc_title="Income Tax Act 2023",
            page_no=24,
            section_id="4",
            chunk_type="section",
            heading_path=["TAX ADMINISTRATION", "4. Income tax authorities.—For the purposes of this Act, there shall be the"],
            text="(a) The National Board of Revenue; (b) Chief Commissioner of Taxes;",
        ),
    ]
    candidate_pool = fused_hits + [
        _hit(
            chunk_id="p024-c057",
            score=0.0,
            doc_id="income-tax-act-2023",
            doc_title="Income Tax Act 2023",
            page_no=24,
            section_id="16",
            chunk_type="section",
            heading_path=["TAX ADMINISTRATION", "4. Income tax authorities.—For the purposes of this Act, there shall be the"],
            text="(l) Tax Recovery Officers nominated by the Commissioner of Taxes;",
        ),
        _hit(
            chunk_id="p025-c058",
            score=0.0,
            doc_id="income-tax-act-2023",
            doc_title="Income Tax Act 2023",
            page_no=25,
            section_id="4",
            chunk_type="section",
            heading_path=["TAX ADMINISTRATION", "4. Income tax authorities.—For the purposes of this Act, there shall be the"],
            text="(m) Assistant Commissioners of Taxes; (n) Extra Assistant Commissioners of Taxes; and (o) Inspectors of Taxes.",
        ),
    ]

    final_hits, _, _, _ = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=3,
        candidate_pool=candidate_pool,
    )

    assert [hit.chunk_id for hit in final_hits] == ["p024-c056", "p024-c057", "p025-c058"]
