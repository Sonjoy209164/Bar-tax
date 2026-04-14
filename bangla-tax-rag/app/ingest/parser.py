import re
import logging
import subprocess
from pathlib import Path
from functools import lru_cache

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
MARKDOWN_TABLE_SEPARATOR = re.compile(r"^\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
BAD_GLYPH_PATTERN = re.compile(r"[·�]")
TABLE_ROW_PATTERN = re.compile(r"^\|.+\|$")
APPENDIX_HEADING_PATTERN = re.compile(
    r"^(?:পরিশিষ্ট|appendix|annex|schedule\b|(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+schedule\b)",
    re.IGNORECASE,
)
PART_HEADING_PATTERN = re.compile(r"^PART\s+[IVXLC0-9]+\s*$", re.IGNORECASE)
CHAPTER_HEADING_PATTERN = re.compile(r"^CHAPTER\s+[IVXLC0-9]+\s*$", re.IGNORECASE)
STATUTE_SECTION_HEADING_PATTERN = re.compile(r"^\d+[A-Za-z]?(?:\.\d+)?\.\s+[A-Z].+", re.IGNORECASE)
CLAUSE_START_PATTERN = re.compile(r"^\(\d+[A-Za-z]?\)\s+")
LETTERED_CLAUSE_START_PATTERN = re.compile(r"^\([a-z]\)\s+", re.IGNORECASE)
GAZETTE_HEADER_PATTERN = re.compile(r"(?:evsjv|†M‡RU|AwZwi³|A‡±vei)")
PAGE_NUMBER_PATTERN = re.compile(r"^\d{4,6}$")

logger = logging.getLogger(__name__)

try:
    import pymupdf4llm
except Exception:  # pragma: no cover - optional dependency
    pymupdf4llm = None


def _looks_like_table(text: str) -> bool:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    normalized_lines = [normalize_text(line) for line in lines]
    serial_count = sum(1 for line in normalized_lines if TABLE_SERIAL_PATTERN.fullmatch(line))
    code_count = sum(1 for line in normalized_lines if TABLE_CODE_PATTERN.fullmatch(line))
    part_or_chapter_count = sum(
        1
        for line in normalized_lines
        if PART_HEADING_PATTERN.match(line) or CHAPTER_HEADING_PATTERN.match(line)
    )
    statute_heading_count = sum(
        1 for line in normalized_lines if STATUTE_SECTION_HEADING_PATTERN.match(line)
    )
    numeric_clause_count = sum(1 for line in normalized_lines if CLAUSE_START_PATTERN.match(line))
    lettered_clause_count = sum(
        1 for line in normalized_lines if LETTERED_CLAUSE_START_PATTERN.match(line)
    )
    clause_count = numeric_clause_count + lettered_clause_count
    definition_line_count = sum(1 for line in normalized_lines if "means" in line.lower())
    quoted_clause_count = sum(1 for line in lines if "“" in line or '"' in line)
    legal_list_signal_count = sum(
        1
        for line in normalized_lines
        if (
            "namely" in line.lower()
            or "shall include" in line.lower()
            or "shall not include" in line.lower()
            or "subject to" in line.lower()
            or "sub-section" in line.lower()
            or "section " in line.lower()
        )
    )
    has_strong_row_structure = serial_count >= 2 and code_count >= 2
    if (
        (part_or_chapter_count or statute_heading_count)
        and clause_count >= 2
        and not has_strong_row_structure
    ):
        return False
    if clause_count >= 4 and code_count == 0 and serial_count == 0:
        return False
    if legal_list_signal_count >= 2 and clause_count >= 2 and not has_strong_row_structure:
        return False
    if statute_heading_count and (clause_count >= 3 or definition_line_count >= 2):
        return False
    if clause_count >= 3 and quoted_clause_count >= 2 and serial_count == 0 and code_count == 0:
        return False
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
        has_strong_row_structure
        or
        repeated_spacing_lines >= max(2, len(lines) // 3)
        or dense_numeric_lines >= max(2, len(lines) // 2)
        or (
            tabular_word_lines >= 2
            and has_header_and_data
            and clause_count <= 1
            and statute_heading_count == 0
            and part_or_chapter_count == 0
        )
    )


def _clean_markdown_text(markdown_text: str) -> str:
    cleaned_lines: list[str] = []
    normalized_text = markdown_text.replace("<br>", "\n")
    for raw_line in normalized_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if MARKDOWN_TABLE_SEPARATOR.fullmatch(line):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("__", "")
        line = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", line)
        if TABLE_ROW_PATTERN.fullmatch(line):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            cells = [cell for cell in cells if cell and cell != " "]
            if cells:
                line = " | ".join(cells)
        line = re.sub(r"\s+\|\s+", " | ", line)
        line = re.sub(r"\s{2,}", " ", line)
        if line:
            cleaned_lines.append(line)
    return normalize_whitespace("\n".join(cleaned_lines))


@lru_cache(maxsize=4)
def _extract_pymupdf4llm_document(pdf_path_str: str) -> dict[int, str]:
    if pymupdf4llm is None:
        return {}
    try:
        page_chunks = pymupdf4llm.to_markdown(
            pdf_path_str,
            ignore_images=True,
            page_chunks=True,
            show_progress=False,
            page_separators=False,
            header=False,
            footer=False,
        ) or []
    except Exception as exc:
        logger.debug("pymupdf4llm document extraction failed for %s: %s", pdf_path_str, exc)
        return {}
    extracted_pages: dict[int, str] = {}
    for page_index, page_chunk in enumerate(page_chunks):
        if not isinstance(page_chunk, dict):
            continue
        extracted_pages[page_index] = _clean_markdown_text(str(page_chunk.get("text") or ""))
    return extracted_pages


def _extract_with_pymupdf4llm(pdf_path: Path, page_number: int) -> str:
    if pymupdf4llm is None:
        return ""
    return _extract_pymupdf4llm_document(str(pdf_path)).get(page_number, "")


@lru_cache(maxsize=4)
def _extract_pdftotext_document(pdf_path_str: str) -> dict[int, str]:
    try:
        completed_process = subprocess.run(
            ["pdftotext", "-layout", pdf_path_str, "-"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        logger.debug("pdftotext unavailable for %s: %s", pdf_path_str, exc)
        return {}
    if completed_process.returncode != 0:
        logger.debug("pdftotext extraction failed for %s: %s", pdf_path_str, completed_process.stderr.strip())
        return {}
    page_texts = completed_process.stdout.split("\f")
    return {
        page_index: normalize_whitespace(page_text)
        for page_index, page_text in enumerate(page_texts)
        if normalize_whitespace(page_text)
    }


def _extract_with_pdftotext(pdf_path: Path, page_number: int) -> str:
    return _extract_pdftotext_document(str(pdf_path)).get(page_number, "")


def _score_extracted_text(text: str) -> float:
    normalized = normalize_whitespace(text)
    if not normalized:
        return float("-inf")
    bangla_char_count = len(re.findall(r"[\u0980-\u09FF]", normalized))
    ascii_word_count = len(re.findall(r"[A-Za-z]{2,}", normalized))
    heading_count = len(re.findall(r"(^|\n)(?:\d+(?:\.\d+)*|ধারা\s*\d+(?:\.\d+)*)", normalized))
    table_signal_count = len(re.findall(r"\b\d{2,4}(?:\.\d{2,4}){1,3}\b", normalized))
    bad_glyph_count = len(BAD_GLYPH_PATTERN.findall(normalized))
    single_char_line_count = sum(1 for line in normalized.splitlines() if len(line.strip()) == 1)
    markdown_pipe_penalty = normalized.count("|") * 0.05
    markdown_heading_bonus = normalized.count("## ") * 1.2
    return (
        len(normalized) * 0.01
        + bangla_char_count * 0.03
        + ascii_word_count * 0.01
        + heading_count * 0.75
        + table_signal_count * 0.15
        + markdown_heading_bonus
        - bad_glyph_count * 1.5
        - single_char_line_count * 0.35
        - markdown_pipe_penalty
    )


def _extract_page_text(pdf_path: Path, plumber_page: pdfplumber.page.Page, fitz_page: fitz.Page) -> str:
    candidate_texts: dict[str, str] = {
        "pdfplumber": normalize_whitespace(plumber_page.extract_text(x_tolerance=2, y_tolerance=3) or ""),
        "pymupdf": normalize_whitespace(fitz_page.get_text("text") or ""),
        "pdftotext": _extract_with_pdftotext(pdf_path, fitz_page.number),
    }
    is_ocr_pdf = pdf_path.name.lower().endswith(".ocr.pdf")
    if pymupdf4llm is not None and not is_ocr_pdf:
        candidate_texts["pymupdf4llm"] = _extract_with_pymupdf4llm(pdf_path, fitz_page.number)

    scored_candidates = {
        backend_name: _score_extracted_text(candidate_text)
        for backend_name, candidate_text in candidate_texts.items()
        if candidate_text.strip()
    }
    if not scored_candidates:
        return ""
    best_backend = max(scored_candidates, key=scored_candidates.get)
    logger.debug(
        "Selected parser backend %s for page %s (scores=%s)",
        best_backend,
        fitz_page.number + 1,
        {name: round(score, 2) for name, score in scored_candidates.items()},
    )
    return candidate_texts[best_backend]


def _is_heading_line(line: str) -> bool:
    normalized_line = normalize_text(line)
    if not normalized_line or PAGE_NUMBER_PATTERN.fullmatch(normalized_line):
        return False
    if GAZETTE_HEADER_PATTERN.search(normalized_line):
        return False
    if PART_HEADING_PATTERN.match(normalized_line) or CHAPTER_HEADING_PATTERN.match(normalized_line):
        return True
    if _is_statute_section_heading_line(normalized_line):
        return True
    return bool(detect_heading_marker(normalized_line))


def _is_statute_section_heading_line(line: str) -> bool:
    return bool(STATUTE_SECTION_HEADING_PATTERN.match(normalize_text(line)))


def _is_appendix_page(raw_text: str, headings: list[str]) -> bool:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    candidate_lines = [*headings, *lines[:15]]
    return any(APPENDIX_HEADING_PATTERN.match(normalize_text(line)) for line in candidate_lines)


def _detect_headings(raw_text: str) -> list[str]:
    headings: list[str] = []
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    found_structural_section_heading = False
    for line in lines[:40]:
        if _is_heading_line(line):
            headings.append(line)
            if _is_statute_section_heading_line(line):
                found_structural_section_heading = True
            continue
        if (
            not found_structural_section_heading
            and (
                APPENDIX_HEADING_PATTERN.match(normalize_text(line))
                or re.match(r"^(উদাহরণ|example)\b", normalize_text(line), re.IGNORECASE)
            )
        ):
            headings.append(line)
    return list(dict.fromkeys(headings))


def build_ocrmypdf_command(
    *,
    input_path: Path,
    output_path: Path,
    language: str,
    force_ocr: bool,
) -> list[str]:
    command = [
        "ocrmypdf",
        "-l",
        language,
        "--optimize",
        "0",
        "--deskew",
        "--output-type",
        "pdf",
    ]
    command.append("--force-ocr" if force_ocr else "--skip-text")
    command.extend([str(input_path), str(output_path)])
    return command


def prepare_pdf_for_ingestion(
    source_path: str,
    *,
    ocr_enabled: bool = False,
    ocr_language: str = "ben+eng",
    ocr_force: bool = True,
    ocr_output_pdf_path: str | None = None,
) -> tuple[Path, Path | None]:
    input_path = Path(source_path)
    if not ocr_enabled:
        return input_path, None
    output_path = Path(ocr_output_pdf_path) if ocr_output_pdf_path else input_path.with_name(f"{input_path.stem}.ocr.pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_ocrmypdf_command(
        input_path=input_path,
        output_path=output_path,
        language=ocr_language,
        force_ocr=ocr_force,
    )
    logger.info("Running OCRmyPDF for Bangla ingestion: %s", " ".join(command))
    completed_process = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed_process.returncode != 0:
        error_message = completed_process.stderr.strip() or completed_process.stdout.strip() or "OCRmyPDF failed."
        raise RuntimeError(f"OCR preparation failed: {error_message}")
    return output_path, output_path


def parse_document(source_path: str) -> list[ParsedPage]:
    pdf_path = Path(source_path)
    parsed_pages: list[ParsedPage] = []
    with pdfplumber.open(pdf_path) as plumber_pdf, fitz.open(pdf_path) as fitz_pdf:
        total_pages = min(len(plumber_pdf.pages), fitz_pdf.page_count)
        for page_index in range(total_pages):
            raw_text = _extract_page_text(pdf_path, plumber_pdf.pages[page_index], fitz_pdf.load_page(page_index))
            normalized_page_text = normalize_text(raw_text)
            headings = _detect_headings(raw_text)
            parsed_pages.append(
                ParsedPage(
                    page_no=page_index + 1,
                    raw_text=raw_text,
                    normalized_text=normalized_page_text,
                    headings=headings,
                    section_markers=extract_section_ids(raw_text),
                    tax_years=extract_tax_years(raw_text),
                    sro_ids=extract_sro_ids(raw_text),
                    is_appendix=_is_appendix_page(raw_text, headings),
                    is_example=bool(EXAMPLE_PATTERN.search(raw_text)),
                    is_table_like=_looks_like_table(raw_text),
                    line_count=len([line for line in raw_text.splitlines() if line.strip()]),
                )
            )
    return parsed_pages
