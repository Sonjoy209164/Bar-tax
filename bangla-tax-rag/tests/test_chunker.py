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


def test_chunker_prefers_structural_section_markers_over_tax_year_numbers() -> None:
    pages = [
        ParsedPage(
            page_no=1,
            raw_text="২০২৫-২০২৬ করবর্ষে কোম্পানির করহার\n২.৩ কোম্পানির জন্য ২০২৫-২০২৬ করবর্ষের করহার\nউক্ত আয়ের ২৫%",
            normalized_text="2025-2026 করবর্ষে কোম্পানির করহার\n2.3 কোম্পানির জন্য 2025-2026 করবর্ষের করহার\nউক্ত আয়ের 25%",
            headings=[],
            section_markers=["2025", "2.3"],
            tax_years=["2025-2026"],
            sro_ids=[],
            is_appendix=False,
            is_example=False,
            is_table_like=True,
            line_count=3,
        )
    ]

    chunks = section_aware_chunking(pages, _sample_metadata(), chunk_size=200)

    assert chunks
    assert chunks[0].section_id == "2"
    assert chunks[0].subsection_id == "2.3"


def test_example_page_lines_are_merged_into_substantive_chunks() -> None:
    pages = [
        ParsedPage(
            page_no=1,
            raw_text="উদাহরণ ১৫\nজনাব করিম একটি কোম্পানিতে চাকরি করেন।\nতাঁর আয় ১২ লক্ষ টাকা।\nতিনি আরও ৫ লক্ষ টাকা বিনিয়োগ করেন।",
            normalized_text="উদাহরণ 15\nজনাব করিম একটি কোম্পানিতে চাকরি করেন।\nতাঁর আয় 12 লক্ষ টাকা।\nতিনি আরও 5 লক্ষ টাকা বিনিয়োগ করেন।",
            headings=["উদাহরণ ১৫"],
            section_markers=[],
            tax_years=["2025-2026"],
            sro_ids=[],
            is_appendix=False,
            is_example=True,
            is_table_like=False,
            line_count=4,
        )
    ]

    chunks = section_aware_chunking(pages, _sample_metadata(), chunk_size=400)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "example"
    assert "জনাব করিম" in chunks[0].normalized_text
    assert "12 লক্ষ টাকা" in chunks[0].normalized_text


def test_structured_table_pages_split_into_row_chunks_without_header_noise() -> None:
    pages = [
        ParsedPage(
            page_no=1,
            raw_text=(
                "আয়কর পররপত্র ২০২৫- ২০২৬ | 100\n"
                "ক্রমিক নং\nমির োনোি\nএইচ এস ককোড\nবণডনা\n(১)\n(২)\n(৩)\n(৪)\n"
                "55.\n12.09\n1209.23.00\nSeeds of forage plants: Fescue seeds\n"
                "56.\n12.09\n1209.24.00\nSeeds of forage plants: Kentucky blue grass seeds\n"
            ),
            normalized_text=(
                "আয়কর পররপত্র 2025- 2026 | 100\n"
                "ক্রমিক নং\nমির োনোি\nএইচ এস ককোড\nবণডনা\n(1)\n(2)\n(3)\n(4)\n"
                "55.\n12.09\n1209.23.00\nSeeds of forage plants: Fescue seeds\n"
                "56.\n12.09\n1209.24.00\nSeeds of forage plants: Kentucky blue grass seeds\n"
            ),
            headings=["55.", "12.09", "1209.23.00"],
            section_markers=["12.09", "1209.23.00", "1209.24.00"],
            tax_years=["2025-2026"],
            sro_ids=[],
            is_appendix=False,
            is_example=False,
            is_table_like=False,
            line_count=16,
        )
    ]

    chunks = section_aware_chunking(pages, _sample_metadata(), chunk_size=400)

    assert len(chunks) == 2
    assert chunks[0].subsection_id == "1209.23.00"
    assert chunks[1].subsection_id == "1209.24.00"
    assert "ক্রমিক নং" not in chunks[0].normalized_text
    assert "আয়কর পররপত্র" not in chunks[0].normalized_text


def test_header_only_blocks_are_dropped() -> None:
    pages = [
        ParsedPage(
            page_no=1,
            raw_text="আয়কর পররপত্র ২০২৫- ২০২৬ | 100\nক্রমিক নং\nমির োনোি\nএইচ এস ককোড\nবণডনা\n(১)\n(২)\n(৩)\n(৪)",
            normalized_text="আয়কর পররপত্র 2025- 2026 | 100\nক্রমিক নং\nমির োনোি\nএইচ এস ককোড\nবণডনা\n(1)\n(2)\n(3)\n(4)",
            headings=[],
            section_markers=["2025", "100", "1", "2", "3", "4"],
            tax_years=["2025-2026"],
            sro_ids=[],
            is_appendix=False,
            is_example=False,
            is_table_like=False,
            line_count=9,
        )
    ]

    chunks = section_aware_chunking(pages, _sample_metadata(), chunk_size=400)

    assert chunks == []
