from types import SimpleNamespace

from app.core.schemas import ChunkRecord, RetrievalHit
from app.retrieval.taxtrail import TaxTrailCorpus, taxtrail_search


def _chunk(
    chunk_id: str,
    *,
    doc_id: str = "btax14_014",
    doc_title: str = "Income Tax Paripatra 2025-2026",
    page_no: int = 1,
    text: str = "করহার",
    tax_year: str | None = None,
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_title=doc_title,
        doc_type="paripatra",
        authority_level="national",
        tax_year=tax_year,
        page_no=page_no,
        section_id=None,
        subsection_id=None,
        appendix_id=None,
        sro_id=None,
        chunk_type="text",
        heading_path=[],
        original_text=text,
        normalized_text=text,
        cross_refs=[],
    )


def _hit(chunk: ChunkRecord, *, score: float = 1.0) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        doc_title=chunk.doc_title,
        page_no=chunk.page_no,
        section_id=chunk.section_id,
        subsection_id=chunk.subsection_id,
        chunk_type=chunk.chunk_type,
        authority_level=chunk.authority_level,
        tax_year=chunk.tax_year,
        original_text=chunk.original_text,
        normalized_text=chunk.normalized_text,
        heading_path=chunk.heading_path,
        content=chunk.original_text,
        score=score,
    )


def test_taxtrail_expands_from_hybrid_seed_to_query_matching_same_document_chunk(monkeypatch) -> None:
    seed = _chunk("btax14_014-p001-c001", text="সূচিপত্র করহার")
    gold = _chunk(
        "btax14_014-p061-c224",
        page_no=61,
        text="বিদেশি ক্রেতার এজেন্ট কমিশন বা পারিশ্রমিক থেকে উৎসে করহার ১০% থেকে ৭.৫% করা হয়েছে।",
    )
    wrong_year = _chunk(
        "btax14_013-p061-c224",
        doc_id="btax14_013",
        doc_title="Income Tax Paripatra 2024-2025",
        page_no=61,
        text="বিদেশি ক্রেতার এজেন্ট কমিশন করহার ১০%",
    )
    corpus = TaxTrailCorpus([seed, gold, wrong_year])

    def fake_hybrid(**_: object) -> SimpleNamespace:
        return SimpleNamespace(final_hits=[_hit(wrong_year, score=2.0), _hit(seed, score=1.0)])

    monkeypatch.setattr("app.retrieval.taxtrail.run_hybrid_retrieval", fake_hybrid)
    monkeypatch.setattr("app.retrieval.taxtrail._load_taxtrail_corpus", lambda _: corpus)

    hits = taxtrail_search(
        "২০২৫-২০২৬ করবর্ষে বিদেশি ক্রেতার এজেন্ট কমিশন থেকে উৎসে করহার কত?",
        top_k=5,
        index_dir="unused",
        dense_index_dir="unused",
    )

    hit_ids = [hit.chunk_id for hit in hits]
    assert "btax14_014-p061-c224" in hit_ids
    assert "btax14_013-p061-c224" not in hit_ids
