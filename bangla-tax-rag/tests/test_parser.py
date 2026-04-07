from pathlib import Path

import fitz

from app.core.utils import (
    extract_section_ids,
    extract_sro_ids,
    extract_tax_years,
    normalize_bangla_digits,
    normalize_text,
    normalize_whitespace,
)
from app.ingest.parser import parse_document


def test_normalization_helpers() -> None:
    sample_text = "করবর্ষ ২০২৫-২০২৬   ধারা ৩.১  এস.আর.ও. নং ১২৩"

    assert normalize_bangla_digits(sample_text) == "করবর্ষ 2025-2026   ধারা 3.1  এস.আর.ও. নং 123"
    assert normalize_whitespace("line 1 \n\n\n line 2") == "line 1 \n\n line 2"
    assert normalize_text("  ২০২৬-২০২৭   ") == "2026-2027"
    assert extract_tax_years(sample_text) == ["2025-2026"]
    assert "ধারা 3.1" in extract_section_ids(sample_text)
    assert extract_sro_ids(sample_text) == ["এস.আর.ও. নং 123"]
    assert extract_sro_ids("Seeds and roots for sowing") == []


def test_parse_document_smoke(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    first_page = document.new_page()
    first_page.insert_text(
        (72, 72),
        "1. Income Tax Guide\nTax year 2025-2026\nSection 3.1 Example\nS.R.O. No 123",
    )
    second_page = document.new_page()
    second_page.insert_text(
        (72, 72),
        "Appendix A\nRate    Amount    Note\n1       1000      sample",
    )
    document.save(pdf_path)
    document.close()

    parsed_pages = parse_document(str(pdf_path))

    assert len(parsed_pages) == 2
    assert parsed_pages[0].page_no == 1
    assert parsed_pages[0].tax_years == ["2025-2026"]
    assert parsed_pages[0].is_example is True
    assert parsed_pages[0].sro_ids == ["S.R.O. No 123"]
    assert parsed_pages[1].is_appendix is True
    assert parsed_pages[1].is_table_like is True
