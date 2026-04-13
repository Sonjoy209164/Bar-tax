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


def test_clause_safe_chunking_keeps_statute_clauses_intact() -> None:
    pages = [
        ParsedPage(
            page_no=1,
            raw_text=(
                "32. Income from employment.—(1) Subject to the provisions of sub-section (2), income from employment shall include the following incomes, namely:—\n"
                "(a) any monetary receipts, salaries and benefits received or receivable from employment;\n"
                "(b) income earned from employee share schemes;\n"
                "(c) untaxed arrear salary; and\n"
                "(d) any amount or benefit received from a past or future employer."
            ),
            normalized_text=(
                "32. Income from employment.—(1) Subject to the provisions of sub-section (2), income from employment shall include the following incomes, namely:—\n"
                "(a) any monetary receipts, salaries and benefits received or receivable from employment;\n"
                "(b) income earned from employee share schemes;\n"
                "(c) untaxed arrear salary; and\n"
                "(d) any amount or benefit received from a past or future employer."
            ),
            headings=["32. Income from employment.—(1) Subject to the provisions of sub-section (2), income from employment shall include the following incomes, namely:—"],
            section_markers=["32"],
            tax_years=[],
            sro_ids=[],
            is_appendix=False,
            is_example=False,
            is_table_like=False,
            line_count=5,
        )
    ]

    chunks = section_aware_chunking(pages, _sample_metadata(), chunk_size=180)

    assert len(chunks) >= 2
    assert any("(a) any monetary receipts" in chunk.normalized_text for chunk in chunks)
    assert any("(b) income earned from employee share schemes;" in chunk.normalized_text for chunk in chunks)
    assert all(not chunk.normalized_text.startswith("ployee share schemes;") for chunk in chunks)
    assert all(not chunk.normalized_text.startswith("ntaxed arrear salary;") for chunk in chunks)


def test_amendment_footnotes_are_trimmed_from_statute_clause_chunks() -> None:
    pages = [
        ParsedPage(
            page_no=24,
            raw_text=(
                "4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities, namely:—\n"
                "(k) Deputy Commissioners of Taxes;\n"
                "(l) Tax Recovery Officers nominated by the Commissioner of Taxes;\n"
                "1 The words and brackets “Director (Central Intelligence Cell)” were substituted by section 16(a) of the Finance Act, 2024.\n"
                "(Act No. V of 2024) with effect from 1st July 2024."
            ),
            normalized_text=(
                "4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities, namely:—\n"
                "(k) Deputy Commissioners of Taxes;\n"
                "(l) Tax Recovery Officers nominated by the Commissioner of Taxes;\n"
                "1 The words and brackets “Director (Central Intelligence Cell)” were substituted by section 16(a) of the Finance Act, 2024.\n"
                "(Act No. V of 2024) with effect from 1st July 2024."
            ),
            headings=["4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities, namely:—"],
            section_markers=["4", "16"],
            tax_years=[],
            sro_ids=[],
            is_appendix=False,
            is_example=False,
            is_table_like=False,
            line_count=5,
        )
    ]

    chunks = section_aware_chunking(pages, _sample_metadata(), chunk_size=500)

    assert len(chunks) == 1
    assert "Finance Act, 2024" not in chunks[0].normalized_text
    assert "(l) Tax Recovery Officers" in chunks[0].normalized_text


def test_statute_sections_are_split_cleanly_and_carried_across_pages() -> None:
    pages = [
        ParsedPage(
            page_no=13,
            raw_text=(
                "evsjv‡`k †M‡RU, AwZwi³, A‡±vei 16, 2025\n"
                "10478\n"
                "PART 2\n"
                "TAX ADMINISTRATION\n"
                "4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities, namely:—\n"
                "(a) The National Board of Revenue;\n"
                "(b) Chief Commissioner of Taxes;\n"
                "(c) Director General (Inspection);"
            ),
            normalized_text=(
                "evsjv‡`k †M‡RU, AwZwi³, A‡±vei 16, 2025\n"
                "10478\n"
                "PART 2\n"
                "TAX ADMINISTRATION\n"
                "4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities, namely:—\n"
                "(a) The National Board of Revenue;\n"
                "(b) Chief Commissioner of Taxes;\n"
                "(c) Director General (Inspection);"
            ),
            headings=["PART 2", "4. Income tax authorities.—For the purposes of this Act, there shall be the following classes of income tax authorities, namely:—"],
            section_markers=["4"],
            tax_years=[],
            sro_ids=[],
            is_appendix=False,
            is_example=False,
            is_table_like=False,
            line_count=8,
        ),
        ParsedPage(
            page_no=14,
            raw_text=(
                "evsjv‡`k †M‡RU, AwZwi³, A‡±vei 16, 2025\n"
                "10479\n"
                "(d) Commissioner of Taxes (Appeals);\n"
                "(e) Commissioner of Taxes (Large Assessee Unit);\n"
                "5. Appointment of income-tax authorities.—(1) Subject to applicable laws, rules and regulations, the income-tax authority shall be appointed.\n"
                "(2) The Board may appoint and post any person as an income-tax authority."
            ),
            normalized_text=(
                "evsjv‡`k †M‡RU, AwZwi³, A‡±vei 16, 2025\n"
                "10479\n"
                "(d) Commissioner of Taxes (Appeals);\n"
                "(e) Commissioner of Taxes (Large Assessee Unit);\n"
                "5. Appointment of income-tax authorities.—(1) Subject to applicable laws, rules and regulations, the income-tax authority shall be appointed.\n"
                "(2) The Board may appoint and post any person as an income-tax authority."
            ),
            headings=["PART 2", "5. Appointment of income-tax authorities.—(1) Subject to applicable laws, rules and regulations, the income-tax authority shall be appointed."],
            section_markers=["5"],
            tax_years=[],
            sro_ids=[],
            is_appendix=False,
            is_example=False,
            is_table_like=False,
            line_count=6,
        ),
    ]

    chunks = section_aware_chunking(pages, _sample_metadata(), chunk_size=500)

    assert len(chunks) == 3
    assert all("evsjv‡" not in chunk.original_text for chunk in chunks)
    assert chunks[0].section_id == "4"
    assert chunks[1].page_no == 14
    assert chunks[1].section_id == "4"
    assert chunks[2].section_id == "5"
    assert chunks[2].chunk_type == "section"
