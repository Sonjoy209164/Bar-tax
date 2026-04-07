from app.core.schemas import ParsedPage
from app.ingest.chunker import (
    chunk_pages,
    example_aware_chunking,
    naive_fixed_chunking,
    section_aware_chunking,
    table_aware_chunking,
    ChunkingMetadata,
)


def _sample_metadata() -> ChunkingMetadata:
    return ChunkingMetadata(
        doc_id="sample-doc",
        doc_title="Sample Tax Circular",
        doc_type="circular",
        authority_level="national",
    )


def _sample_pages() -> list[ParsedPage]:
    return [
        ParsedPage(
            page_no=1,
            raw_text="1. General Provisions\nTax year 2025-2026\nSection 1.1 covers scope.\nধারা 3.1 cross ref",
            normalized_text="1. General Provisions\nTax year 2025-2026\nSection 1.1 covers scope.\nধারা 3.1 cross ref",
            headings=["1. General Provisions"],
            section_markers=["1", "1.1", "ধারা 3.1"],
            tax_years=["2025-2026"],
            sro_ids=[],
            is_appendix=False,
            is_example=False,
            is_table_like=False,
            line_count=4,
        ),
        ParsedPage(
            page_no=2,
            raw_text="উদাহরণ\nকর গণনার উদাহরণ এখানে দেওয়া আছে।",
            normalized_text="উদাহরণ\nকর গণনার উদাহরণ এখানে দেওয়া আছে।",
            headings=["উদাহরণ"],
            section_markers=[],
            tax_years=[],
            sro_ids=[],
            is_appendix=False,
            is_example=True,
            is_table_like=False,
            line_count=2,
        ),
        ParsedPage(
            page_no=3,
            raw_text="পরিশিষ্ট ক\nহার    পরিমাণ    মন্তব্য\n১      ১০০০      নমুনা",
            normalized_text="পরিশিষ্ট ক\nহার পরিমাণ মন্তব্য\n1 1000 নমুনা",
            headings=["পরিশিষ্ট ক"],
            section_markers=["পরিশিষ্ট ক"],
            tax_years=[],
            sro_ids=[],
            is_appendix=True,
            is_example=False,
            is_table_like=True,
            line_count=3,
        ),
    ]


def test_naive_fixed_chunking_returns_chunks() -> None:
    chunks = naive_fixed_chunking(_sample_pages(), _sample_metadata(), chunk_size=80)

    assert chunks
    assert chunks[0].doc_id == "sample-doc"
    assert chunks[0].chunk_type == "fixed"


def test_section_aware_chunking_tracks_heading_path() -> None:
    chunks = section_aware_chunking(_sample_pages(), _sample_metadata(), chunk_size=120)

    assert chunks
    assert chunks[0].heading_path == ["1. General Provisions"]
    assert chunks[0].tax_year == "2025-2026"


def test_example_and_table_aware_chunking_assign_chunk_types() -> None:
    example_chunks = example_aware_chunking(_sample_pages(), _sample_metadata(), chunk_size=120)
    table_chunks = table_aware_chunking(_sample_pages(), _sample_metadata(), chunk_size=120)

    assert any(chunk.chunk_type == "example" for chunk in example_chunks)
    assert any(chunk.chunk_type == "table" for chunk in table_chunks)


def test_chunk_pages_defaults_to_section_aware() -> None:
    chunks = chunk_pages(
        _sample_pages(),
        doc_id="sample-doc",
        doc_title="Sample Tax Circular",
        doc_type="circular",
        authority_level="national",
    )

    assert chunks
    assert chunks[0].chunk_type in {"section", "text", "appendix", "example", "table"}
