from pathlib import Path

from app.core.schemas import ChunkRecord
from app.core.utils import preprocess_query
from app.retrieval.filters import authority_value, filter_chunk_records
from app.retrieval.sparse import (
    apply_score_boosts,
    build_sparse_index,
    load_sparse_index,
    save_sparse_index,
    search_sparse_index,
)


def _chunk(
    *,
    chunk_id: str,
    doc_id: str,
    doc_title: str,
    authority_level: str,
    tax_year: str | None,
    page_no: int,
    section_id: str | None,
    subsection_id: str | None,
    chunk_type: str,
    heading_path: list[str],
    normalized_text: str,
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_title=doc_title,
        doc_type="circular",
        authority_level=authority_level,
        tax_year=tax_year,
        effective_start=None,
        effective_end=None,
        page_no=page_no,
        section_id=section_id,
        subsection_id=subsection_id,
        appendix_id=None,
        sro_id=None,
        chunk_type=chunk_type,
        heading_path=heading_path,
        original_text=normalized_text,
        normalized_text=normalized_text,
        cross_refs=[],
    )


def _dataset() -> list[ChunkRecord]:
    return [
        _chunk(
            chunk_id="c1",
            doc_id="doc-2025",
            doc_title="Income Tax Circular 2025-2026",
            authority_level="national",
            tax_year="2025-2026",
            page_no=1,
            section_id="3",
            subsection_id="3.1",
            chunk_type="table",
            heading_path=["ধারা 3.1", "করহার"],
            normalized_text="ধারা 3.1 অনুযায়ী 2025-2026 করহার 10 শতাংশ",
        ),
        _chunk(
            chunk_id="c2",
            doc_id="doc-2024",
            doc_title="Income Tax Circular 2024-2025",
            authority_level="regional",
            tax_year="2024-2025",
            page_no=2,
            section_id="3",
            subsection_id="3.1",
            chunk_type="table",
            heading_path=["ধারা 3.1", "করহার"],
            normalized_text="ধারা 3.1 অনুযায়ী 2024-2025 করহার 12 শতাংশ",
        ),
        _chunk(
            chunk_id="c3",
            doc_id="doc-example",
            doc_title="Worked Example Note",
            authority_level="national",
            tax_year="2025-2026",
            page_no=3,
            section_id="8",
            subsection_id="8.1",
            chunk_type="example",
            heading_path=["উদাহরণ"],
            normalized_text="উদাহরণ সহ কর গণনার পদ্ধতি",
        ),
    ]


def test_query_normalization_and_signal_extraction() -> None:
    signals = preprocess_query("  ২০২৫-২০২৬ ধারা ৩.১ উদাহরণ  ")

    assert signals.normalized_query == "2025-2026 ধারা 3.1 উদাহরণ"
    assert signals.tax_year == "2025-2026"
    assert signals.section_reference == "3.1"
    assert signals.query_type == "example"


def test_query_without_section_does_not_treat_tax_year_as_section() -> None:
    signals = preprocess_query("২০২৫-২০২৬ করবর্ষে কোম্পানির করহার কী?")

    assert signals.tax_year == "2025-2026"
    assert signals.section_reference is None
    assert signals.section_id is None
    assert signals.subsection_id is None


def test_filtering_by_tax_year() -> None:
    filtered = filter_chunk_records(_dataset(), tax_year="2025-2026")

    assert {chunk.chunk_id for chunk in filtered} == {"c1", "c3"}


def test_section_match_boost_and_authority_boost() -> None:
    query_signals = preprocess_query("ধারা 3.1 করহার")
    high_authority_score = apply_score_boosts(_dataset()[0], query_signals, 1.0)
    lower_authority_score = apply_score_boosts(_dataset()[1], query_signals, 1.0)

    assert high_authority_score > lower_authority_score
    assert authority_value("national") > authority_value("regional")


def test_sparse_retrieval_on_synthetic_dataset(tmp_path: Path) -> None:
    sparse_index = build_sparse_index(_dataset())
    save_sparse_index(sparse_index, tmp_path / "sparse")
    loaded_index = load_sparse_index(tmp_path / "sparse")

    response = search_sparse_index(
        query="২০২৫-২০২৬ ধারা ৩.১ করহার",
        index=loaded_index,
        top_k=2,
    )

    assert response.hits
    assert response.hits[0].chunk_id == "c1"
    assert response.hits[0].tax_year == "2025-2026"


def test_graceful_empty_results_after_filtering() -> None:
    response = search_sparse_index(
        query="করহার",
        index=build_sparse_index(_dataset()),
        top_k=3,
        tax_year="2030-2031",
    )

    assert response.hits == []
