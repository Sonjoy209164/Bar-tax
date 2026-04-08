from pathlib import Path
from subprocess import CompletedProcess

import fitz
import pytest

from app.core.utils import (
    extract_section_ids,
    extract_sro_ids,
    extract_tax_years,
    normalize_bangla_digits,
    normalize_text,
    normalize_whitespace,
)
from app.ingest.parser import build_ocrmypdf_command, parse_document, prepare_pdf_for_ingestion


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


def test_parse_document_keeps_statute_definition_pages_out_of_appendix_mode(tmp_path: Path) -> None:
    pdf_path = tmp_path / "statute.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        (
            "PART I\n"
            "PRELIMINARY\n"
            "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—\n"
            "(1) “Commissioner” means Commissioner of Taxes referred to in section 4;\n"
            "(2) “written down value” means the written down value as defined in Part 1 of the Third Schedule;"
        ),
    )
    document.save(pdf_path)
    document.close()

    parsed_pages = parse_document(str(pdf_path))

    assert len(parsed_pages) == 1
    assert parsed_pages[0].is_appendix is False
    assert parsed_pages[0].is_table_like is False
    assert any("2. Definitions" in heading for heading in parsed_pages[0].headings)


def test_build_ocrmypdf_command_uses_bengali_force_ocr(tmp_path: Path) -> None:
    input_path = tmp_path / "input.pdf"
    output_path = tmp_path / "output.ocr.pdf"

    command = build_ocrmypdf_command(
        input_path=input_path,
        output_path=output_path,
        language="ben+eng",
        force_ocr=True,
    )

    assert command[:3] == ["ocrmypdf", "-l", "ben+eng"]
    assert "--force-ocr" in command
    assert str(input_path) in command
    assert str(output_path) in command


def test_prepare_pdf_for_ingestion_runs_ocr_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"%PDF-1.4\n")
    output_path = tmp_path / "output.ocr.pdf"

    def fake_run(command, check, capture_output, text):  # type: ignore[no-untyped-def]
        output_path.write_bytes(b"%PDF-1.4 OCR\n")
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("app.ingest.parser.subprocess.run", fake_run)

    parse_input_path, ocr_output_path = prepare_pdf_for_ingestion(
        str(input_path),
        ocr_enabled=True,
        ocr_language="ben+eng",
        ocr_force=True,
        ocr_output_pdf_path=str(output_path),
    )

    assert parse_input_path == output_path
    assert ocr_output_path == output_path
    assert output_path.exists()
