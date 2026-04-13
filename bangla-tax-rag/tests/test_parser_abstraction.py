from pathlib import Path

import fitz

from app.ingestion import (
    FallbackDocumentParser,
    LlamaParseDocumentParser,
    build_parser,
    build_parsed_page_from_text,
)


def test_build_parsed_page_from_text_applies_existing_page_heuristics() -> None:
    page = build_parsed_page_from_text(
        1,
        "PART I\n2. Definitions.\nCommissioner means Commissioner of Taxes.\n",
    )

    assert page.page_no == 1
    assert any("2. Definitions" in heading for heading in page.headings)
    assert page.is_table_like is False


def test_fallback_document_parser_wraps_legacy_parser(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "1. Income Tax Guide\nTax year 2025-2026\nSection 3.1 Example")
    document.save(pdf_path)
    document.close()

    parser = FallbackDocumentParser()
    parsed = parser.parse(pdf_path)

    assert parsed.parser_provider == "fallback"
    assert parsed.parser_metadata["page_count"] == 1
    assert parsed.pages[0].tax_years == ["2025-2026"]


def test_build_parser_uses_fallback_by_default() -> None:
    parser = build_parser("fallback")

    assert isinstance(parser, FallbackDocumentParser)


def test_build_parser_falls_back_when_llamaparse_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.ingestion.llamaparse_parser._load_llamaparse_class", lambda: None)

    parser = build_parser("llamaparse", allow_fallback=True, api_key="llx-demo")

    assert isinstance(parser, FallbackDocumentParser)


def test_llamaparse_parser_converts_documents_to_pages(monkeypatch, tmp_path: Path) -> None:
    class FakeDocument:
        def __init__(self, text: str, metadata: dict):
            self.text = text
            self.metadata = metadata

    class FakeLlamaParse:
        def __init__(self, api_key: str, result_type: str, verbose: bool):
            self.api_key = api_key
            self.result_type = result_type
            self.verbose = verbose

        def load_data(self, path: str):
            return [
                FakeDocument("PART I\n2. Definitions.\nCommissioner means Commissioner of Taxes.", {"page_number": 1}),
                FakeDocument("Appendix A\nRate | Amount | Note", {"page_number": 2}),
            ]

    monkeypatch.setattr("app.ingestion.llamaparse_parser._load_llamaparse_class", lambda: FakeLlamaParse)

    parser = LlamaParseDocumentParser(api_key="llx-demo", result_type="markdown")
    parsed = parser.parse(tmp_path / "income-tax-act.pdf")

    assert parsed.parser_provider == "llamaparse"
    assert parsed.parser_metadata["page_count"] == 2
    assert parsed.raw_markdown is not None
    assert parsed.pages[0].page_no == 1
    assert parsed.pages[1].is_appendix is True
