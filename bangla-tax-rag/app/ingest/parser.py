import re
from pathlib import Path

import fitz
import pdfplumber

from app.core.schemas import ParsedPage
from app.core.utils import (
    detect_heading_marker,
    extract_section_ids,
    extract_sro_ids,
    extract_tax_years,
    normalize_text,
    normalize_whitespace,
)

APPENDIX_PATTERN = re.compile(r"(পরিশিষ্ট|appendix|annex|schedule)", re.IGNORECASE)
EXAMPLE_PATTERN = re.compile(r"(উদাহরণ|example|illustration)", re.IGNORECASE)
TABLE_CODE_PATTERN = re.compile(r"^\d{2,4}(?:\.\d{2,4}){1,3}$")
TABLE_SERIAL_PATTERN = re.compile(r"^\d+\.$")

try:
    import pymupdf4llm
except Exception:  # pragma: no cover - optional dependency
    pymupdf4llm = None


def _looks_like_table(text: str) -> bool:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    serial_count = sum(1 for line in lines if TABLE_SERIAL_PATTERN.fullmatch(normalize_text(line)))
    code_count = sum(1 for line in lines if TABLE_CODE_PATTERN.fullmatch(normalize_text(line)))
    repeated_spacing_lines = sum(1 for line in lines if re.search(r"\S\s{3,}\S", line))
    dense_numeric_lines = sum(
        1
        for line in lines
        if len(re.findall(r"\d", line)) >= 3 and len(line.split()) >= 3
    )
    tabular_word_lines = sum(1 for line in lines if len(line.split()) >= 3)
    has_header_and_data = len(lines) >= 3 and len(lines[1].split()) >= 3 and any(
        re.search(r"\d", line) for line in lines[2:]
    )
    return (
        (serial_count >= 2 and code_count >= 2)
        or
        repeated_spacing_lines >= max(2, len(lines) // 3)
        or dense_numeric_lines >= max(2, len(lines) // 2)
        or (tabular_word_lines >= 2 and has_header_and_data)
    )


def _extract_page_text(plumber_page: pdfplumber.page.Page, fitz_page: fitz.Page) -> str:
    if pymupdf4llm is not None:
        try:
            markdown_text = pymupdf4llm.to_markdown(fitz_page.parent, pages=[fitz_page.number]) or ""
            if len(markdown_text.strip()) >= 40:
                return normalize_whitespace(markdown_text)
        except Exception:
            pass
    plumber_text = plumber_page.extract_text(x_tolerance=2, y_tolerance=3) or ""
    fitz_text = fitz_page.get_text("text") or ""
    candidate_text = plumber_text if len(plumber_text.strip()) >= len(fitz_text.strip()) else fitz_text
    return normalize_whitespace(candidate_text)


def _detect_headings(raw_text: str) -> list[str]:
    headings: list[str] = []
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for line in lines[:12]:
        heading_marker = detect_heading_marker(line)
        if heading_marker:
            headings.append(line)
            continue
        if APPENDIX_PATTERN.search(line) or EXAMPLE_PATTERN.search(line):
            headings.append(line)
    return list(dict.fromkeys(headings))


def parse_document(source_path: str) -> list[ParsedPage]:
    pdf_path = Path(source_path)
    parsed_pages: list[ParsedPage] = []
    with pdfplumber.open(pdf_path) as plumber_pdf, fitz.open(pdf_path) as fitz_pdf:
        total_pages = min(len(plumber_pdf.pages), fitz_pdf.page_count)
        for page_index in range(total_pages):
            raw_text = _extract_page_text(plumber_pdf.pages[page_index], fitz_pdf.load_page(page_index))
            normalized_page_text = normalize_text(raw_text)
            parsed_pages.append(
                ParsedPage(
                    page_no=page_index + 1,
                    raw_text=raw_text,
                    normalized_text=normalized_page_text,
                    headings=_detect_headings(raw_text),
                    section_markers=extract_section_ids(raw_text),
                    tax_years=extract_tax_years(raw_text),
                    sro_ids=extract_sro_ids(raw_text),
                    is_appendix=bool(APPENDIX_PATTERN.search(raw_text)),
                    is_example=bool(EXAMPLE_PATTERN.search(raw_text)),
                    is_table_like=_looks_like_table(raw_text),
                    line_count=len([line for line in raw_text.splitlines() if line.strip()]),
                )
            )
    return parsed_pages
