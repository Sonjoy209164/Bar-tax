from collections.abc import Iterable
from dataclasses import dataclass
import re

from app.core.schemas import ChunkRecord, ParsedPage
from app.core.utils import extract_cross_references, normalize_text, select_primary_section_markers


DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 120
MIN_BLOCK_LENGTH = 120
TABLE_CODE_PATTERN = re.compile(r"^\d{2,4}(?:\.\d{2,4}){1,3}$")
TABLE_SERIAL_PATTERN = re.compile(r"^\d+\.$")
PURE_STRUCTURAL_LINE_PATTERN = re.compile(r"^(?:\(?[0-9]+\)?|[|:.\-–—/ ]+)$")
ENGLISH_GAZETTE_HEADER_PATTERN = re.compile(r"(?:evsjv|†M‡RU|AwZwi³|A‡±vei)")
PAGE_NUMBER_LINE_PATTERN = re.compile(r"^\d{4,6}$")
PART_HEADING_PATTERN = re.compile(r"^PART\s+[IVXLC0-9]+\s*$", re.IGNORECASE)
CHAPTER_HEADING_PATTERN = re.compile(r"^CHAPTER\s+[IVXLC0-9]+\s*$", re.IGNORECASE)
STATUTE_SECTION_HEADING_PATTERN = re.compile(r"^\d+[A-Za-z]?(?:\.\d+)?\.\s+[A-Z].+", re.IGNORECASE)
CLAUSE_START_PATTERN = re.compile(r"^\(\d+[A-Za-z]?\)\s+")
ALL_CAPS_CONTEXT_PATTERN = re.compile(r"^[A-Z][A-Z\s,&/-]{2,}$")
ALPHA_CLAUSE_PATTERN = re.compile(r"^\([a-z]\)\s+", re.IGNORECASE)
ROMAN_CLAUSE_PATTERN = re.compile(r"^\((?:[ivxlcdm]+)\)\s+", re.IGNORECASE)
ROMAN_NUMERAL_HEADING_PATTERN = re.compile(r"^(?:[ivxlcdm]+)[.)]\s+", re.IGNORECASE)
AMENDMENT_FOOTNOTE_START_PATTERN = re.compile(
    r"^\d+\s+(?:The words?|The figures?|The brackets?|The punctuation|The sentence|The paragraph|The expression)\b",
    re.IGNORECASE,
)


def _is_document_header_line(line: str) -> bool:
    normalized_line = normalize_text(line)
    if not normalized_line:
        return True
    if ENGLISH_GAZETTE_HEADER_PATTERN.search(normalized_line):
        return True
    if PAGE_NUMBER_LINE_PATTERN.fullmatch(normalized_line):
        return True
    if normalized_line.startswith("আয়কর পররপত্র"):
        return True
    if normalized_line in {
        "ক্রমিক নং",
        "মির োনোি",
        "এইচ এস ককোড",
        "বণডনা",
        "(1)",
        "(2)",
        "(3)",
        "(4)",
    }:
        return True
    return False


def _is_context_heading_line(line: str) -> bool:
    normalized_line = normalize_text(line)
    return bool(
        PART_HEADING_PATTERN.match(normalized_line)
        or CHAPTER_HEADING_PATTERN.match(normalized_line)
        or ALL_CAPS_CONTEXT_PATTERN.fullmatch(normalized_line)
    )


def _is_statute_section_heading_line(line: str) -> bool:
    normalized_line = normalize_text(line)
    return bool(STATUTE_SECTION_HEADING_PATTERN.match(normalized_line))


def _page_prefers_section_chunks(page: ParsedPage, lines: list[str]) -> bool:
    clause_count = sum(1 for line in lines if CLAUSE_START_PATTERN.match(normalize_text(line)))
    alpha_clause_count = sum(1 for line in lines if ALPHA_CLAUSE_PATTERN.match(normalize_text(line)))
    quoted_clause_count = sum(1 for line in lines if "“" in line or '"' in line)
    if any(_is_statute_section_heading_line(line) for line in lines):
        return True
    if any(_is_context_heading_line(line) for line in lines[:15]):
        return True
    if page.headings and any(_is_statute_section_heading_line(heading) for heading in page.headings):
        return True
    if clause_count >= 3 and quoted_clause_count >= 2:
        return True
    if alpha_clause_count >= 3:
        return True
    return False


def _is_low_value_chunk_text(text: str) -> bool:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return True
    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    if not lines:
        return True
    if all(_is_document_header_line(line) or PURE_STRUCTURAL_LINE_PATTERN.fullmatch(line) for line in lines):
        return True
    if len(normalized_text) < 20 and all(not character.isalpha() for character in normalized_text):
        return True
    return False


def _clean_chunk_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    while lines and _is_document_header_line(lines[0]):
        lines.pop(0)
    while lines and _is_document_header_line(lines[-1]):
        lines.pop()
    while lines and _is_context_heading_line(lines[0]):
        lines.pop(0)
    while lines and _is_context_heading_line(lines[-1]):
        lines.pop()
    while lines and PURE_STRUCTURAL_LINE_PATTERN.fullmatch(normalize_text(lines[0])):
        lines.pop(0)
    while lines and PURE_STRUCTURAL_LINE_PATTERN.fullmatch(normalize_text(lines[-1])):
        lines.pop()
    footnote_start_index = next(
        (index for index, line in enumerate(lines) if _is_amendment_footnote_start_line(line)),
        None,
    )
    if footnote_start_index is not None:
        lines = lines[:footnote_start_index]
    return "\n".join(lines).strip()


def _is_amendment_footnote_start_line(line: str) -> bool:
    normalized_line = normalize_text(line)
    return bool(AMENDMENT_FOOTNOTE_START_PATTERN.match(normalized_line))


def _looks_like_structured_table_page(lines: list[str]) -> bool:
    serial_count = sum(1 for line in lines if TABLE_SERIAL_PATTERN.fullmatch(normalize_text(line)))
    code_count = sum(1 for line in lines if TABLE_CODE_PATTERN.fullmatch(normalize_text(line)))
    return serial_count >= 2 and code_count >= 2


def _build_structured_table_blocks(page: ParsedPage, lines: list[str]) -> list[tuple[str, list[str], str]]:
    cleaned_lines = [line for line in lines if not _is_document_header_line(line)]
    blocks: list[tuple[str, list[str], str]] = []
    current_lines: list[str] = []
    current_heading_path: list[str] = []
    last_major_code: str | None = None
    for line in cleaned_lines:
        normalized_line = normalize_text(line)
        if TABLE_SERIAL_PATTERN.fullmatch(normalized_line):
            if current_lines:
                blocks.append(("\n".join(current_lines), list(current_heading_path), "appendix" if page.is_appendix else "table"))
                current_lines = []
            current_heading_path = [normalized_line]
            if last_major_code:
                current_heading_path.append(last_major_code)
            current_lines.append(line)
            continue
        if TABLE_CODE_PATTERN.fullmatch(normalized_line):
            if re.fullmatch(r"\d{2}\.\d{2}", normalized_line):
                last_major_code = normalized_line
            if not current_heading_path:
                current_heading_path = [normalized_line]
            elif normalized_line not in current_heading_path:
                current_heading_path.append(normalized_line)
            current_lines.append(line)
            continue
        if current_lines:
            current_lines.append(line)
    if current_lines:
        blocks.append(("\n".join(current_lines), list(current_heading_path), "appendix" if page.is_appendix else "table"))
    return blocks


@dataclass
class ChunkingMetadata:
    doc_id: str
    doc_title: str
    doc_type: str
    authority_level: str


def _split_text_with_overlap(text: str, chunk_size: int, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    normalized_input = text.strip()
    if not normalized_input:
        return []
    segments = _segment_text_for_chunking(normalized_input)
    if len(segments) <= 1:
        slices: list[str] = []
        start_index = 0
        text_length = len(normalized_input)
        while start_index < text_length:
            end_index = min(text_length, start_index + chunk_size)
            slices.append(normalized_input[start_index:end_index].strip())
            if end_index >= text_length:
                break
            start_index = max(end_index - overlap, start_index + 1)
        return [slice_text for slice_text in slices if slice_text]

    slices: list[str] = []
    current_segments: list[str] = []
    current_length = 0
    for segment in segments:
        segment_text = segment.strip()
        if not segment_text:
            continue
        segment_length = len(segment_text)
        separator_length = 1 if current_segments else 0
        would_exceed = current_segments and current_length + separator_length + segment_length > chunk_size
        if would_exceed:
            slices.append("\n".join(current_segments).strip())
            current_segments = _overlap_segments(current_segments, overlap)
            current_length = sum(len(item) for item in current_segments) + max(len(current_segments) - 1, 0)
        if segment_length > chunk_size and not current_segments:
            start_index = 0
            while start_index < segment_length:
                end_index = min(segment_length, start_index + chunk_size)
                slices.append(segment_text[start_index:end_index].strip())
                if end_index >= segment_length:
                    break
                start_index = max(end_index - overlap, start_index + 1)
            current_segments = []
            current_length = 0
            continue
        if current_segments:
            current_length += 1
        current_segments.append(segment_text)
        current_length += segment_length
    if current_segments:
        slices.append("\n".join(current_segments).strip())
    return [slice_text for slice_text in slices if slice_text]


def _line_starts_new_legal_unit(line: str) -> bool:
    normalized_line = normalize_text(line)
    if not normalized_line:
        return False
    return bool(
        _is_statute_section_heading_line(line)
        or CLAUSE_START_PATTERN.match(normalized_line)
        or ALPHA_CLAUSE_PATTERN.match(normalized_line)
        or ROMAN_CLAUSE_PATTERN.match(normalized_line)
        or ROMAN_NUMERAL_HEADING_PATTERN.match(normalized_line)
    )


def _segment_text_for_chunking(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return [text.strip()]
    segments: list[str] = []
    current_lines: list[str] = []
    for line in lines:
        if current_lines and _line_starts_new_legal_unit(line):
            segments.append("\n".join(current_lines).strip())
            current_lines = [line]
            continue
        current_lines.append(line)
    if current_lines:
        segments.append("\n".join(current_lines).strip())
    return segments


def _overlap_segments(segments: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or not segments:
        return []
    retained_segments: list[str] = []
    retained_length = 0
    for segment in reversed(segments):
        projected_length = retained_length + len(segment) + (1 if retained_segments else 0)
        if retained_segments and projected_length > overlap:
            break
        retained_segments.insert(0, segment)
        retained_length = projected_length
        if retained_length >= overlap:
            break
    return retained_segments


def _derive_effective_dates(tax_year: str | None) -> tuple[str | None, str | None]:
    if not tax_year or "-" not in tax_year:
        return None, None
    start_year, end_year = tax_year.split("-", maxsplit=1)
    return f"{start_year}-07-01", f"{end_year}-06-30"


def _build_chunk_record(
    *,
    page: ParsedPage,
    metadata: ChunkingMetadata,
    chunk_index: int,
    chunk_text: str,
    heading_path: list[str],
    chunk_type: str,
) -> ChunkRecord:
    cleaned_chunk_text = _clean_chunk_text(chunk_text)
    section_id, subsection_id = select_primary_section_markers(
        cleaned_chunk_text,
        heading_path=heading_path,
        page_section_markers=page.section_markers,
    )
    appendix_id = next(
        (marker for marker in page.section_markers if marker.lower().startswith("পরিশিষ্ট")),
        None,
    )
    tax_year = page.tax_years[0] if page.tax_years else None
    effective_start, effective_end = _derive_effective_dates(tax_year)
    sro_id = page.sro_ids[0] if page.sro_ids else None
    normalized_chunk_text = normalize_text(cleaned_chunk_text)
    return ChunkRecord(
        chunk_id=f"{metadata.doc_id}-p{page.page_no:03d}-c{chunk_index:03d}",
        doc_id=metadata.doc_id,
        doc_title=metadata.doc_title,
        doc_type=metadata.doc_type,
        authority_level=metadata.authority_level,
        tax_year=tax_year,
        effective_start=effective_start,
        effective_end=effective_end,
        page_no=page.page_no,
        section_id=section_id,
        subsection_id=subsection_id,
        appendix_id=appendix_id,
        sro_id=sro_id,
        chunk_type=chunk_type,
        heading_path=heading_path,
        original_text=cleaned_chunk_text,
        normalized_text=normalized_chunk_text,
        cross_refs=extract_cross_references(cleaned_chunk_text),
    )


def _iter_page_blocks(page: ParsedPage) -> Iterable[tuple[str, list[str], str]]:
    lines = [line.strip() for line in page.raw_text.splitlines() if line.strip()]
    if not lines:
        return
    if _looks_like_structured_table_page(lines):
        yield from _build_structured_table_blocks(page, lines)
        return
    page_prefers_section = _page_prefers_section_chunks(page, lines)
    section_context: list[str] = []
    active_heading_path: list[str] = []
    current_lines: list[str] = []
    current_type = (
        "example"
        if page.is_example
        else "table"
        if page.is_table_like
        else "appendix"
        if page.is_appendix
        else "section"
        if page_prefers_section
        else "text"
    )
    for line in lines:
        if _is_document_header_line(line):
            continue
        if _is_context_heading_line(line):
            if current_lines:
                yield "\n".join(current_lines), list(active_heading_path), current_type
                current_lines = []
            section_context = [line]
            if not active_heading_path:
                active_heading_path = list(section_context)
            continue
        if line in page.headings or _is_statute_section_heading_line(line):
            if current_lines:
                yield "\n".join(current_lines), list(active_heading_path), current_type
                current_lines = []
            active_heading_path = [*section_context, line] if section_context else [line]
            current_type = "section" if page_prefers_section else (
                "example"
                if page.is_example
                else "table"
                if page.is_table_like
                else "appendix"
                if page.is_appendix
                else "section"
            )
            current_lines.append(line)
            continue
        if (
            CLAUSE_START_PATTERN.match(normalize_text(line))
            and current_lines
            and "definitions" in " ".join(active_heading_path).lower()
            and (len(current_lines) > 1 or len("\n".join(current_lines)) >= MIN_BLOCK_LENGTH)
        ):
            yield "\n".join(current_lines), list(active_heading_path), current_type
            current_lines = [line]
            continue
        if ("উদাহরণ" in line or "example" in line.lower()) and not page.is_example:
            if current_lines:
                yield "\n".join(current_lines), list(active_heading_path), current_type
                current_lines = []
            current_type = "example"
        current_lines.append(line)
    if current_lines:
        yield "\n".join(current_lines), list(active_heading_path), current_type


def _merge_small_blocks(
    page_blocks: list[tuple[str, list[str], str]],
    *,
    min_block_length: int = MIN_BLOCK_LENGTH,
) -> list[tuple[str, list[str], str]]:
    merged_blocks: list[tuple[str, list[str], str]] = []
    pending_text = ""
    pending_heading_path: list[str] = []
    pending_type = "text"

    def flush_pending() -> None:
        nonlocal pending_text, pending_heading_path, pending_type
        if pending_text.strip():
            merged_blocks.append((pending_text.strip(), list(pending_heading_path), pending_type))
        pending_text = ""
        pending_heading_path = []
        pending_type = "text"

    for block_text, heading_path, chunk_type in page_blocks:
        stripped_block = block_text.strip()
        if not stripped_block:
            continue
        if not pending_text:
            pending_text = stripped_block
            pending_heading_path = list(heading_path)
            pending_type = chunk_type
            continue
        same_shape = pending_type == chunk_type and pending_heading_path == list(heading_path)
        if len(pending_text) < min_block_length or len(stripped_block) < min_block_length:
            if same_shape:
                pending_text = f"{pending_text}\n{stripped_block}".strip()
                continue
        flush_pending()
        pending_text = stripped_block
        pending_heading_path = list(heading_path)
        pending_type = chunk_type
    flush_pending()
    return merged_blocks


def naive_fixed_chunking(
    pages: list[ParsedPage],
    metadata: ChunkingMetadata,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    chunk_counter = 1
    for page in pages:
        for piece in _split_text_with_overlap(page.raw_text, chunk_size):
            chunks.append(
                _build_chunk_record(
                    page=page,
                    metadata=metadata,
                    chunk_index=chunk_counter,
                    chunk_text=piece,
                    heading_path=page.headings,
                    chunk_type="fixed",
                )
            )
            chunk_counter += 1
    return chunks


def section_aware_chunking(
    pages: list[ParsedPage],
    metadata: ChunkingMetadata,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    chunk_counter = 1
    carry_heading_path: list[str] = []
    carry_chunk_type = "section"
    for page in pages:
        page_blocks = list(_merge_small_blocks(list(_iter_page_blocks(page))))
        resolved_blocks: list[tuple[str, list[str], str]] = []
        for block_index, (block_text, heading_path, chunk_type) in enumerate(page_blocks):
            effective_heading_path = list(heading_path)
            effective_chunk_type = chunk_type
            if block_index == 0 and not effective_heading_path and carry_heading_path:
                effective_heading_path = list(carry_heading_path)
                if effective_chunk_type in {"text", "appendix", "table"} and carry_chunk_type == "section":
                    effective_chunk_type = carry_chunk_type
            if effective_heading_path:
                carry_heading_path = list(effective_heading_path)
                carry_chunk_type = effective_chunk_type
            resolved_blocks.append((block_text, effective_heading_path, effective_chunk_type))
        for block_text, heading_path, chunk_type in resolved_blocks:
            for piece in _split_text_with_overlap(block_text, chunk_size):
                if _is_low_value_chunk_text(piece):
                    continue
                chunks.append(
                    _build_chunk_record(
                        page=page,
                        metadata=metadata,
                        chunk_index=chunk_counter,
                        chunk_text=piece,
                        heading_path=heading_path,
                        chunk_type=chunk_type,
                    )
                )
                chunk_counter += 1
    return chunks


def example_aware_chunking(
    pages: list[ParsedPage],
    metadata: ChunkingMetadata,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[ChunkRecord]:
    base_chunks = section_aware_chunking(pages, metadata, chunk_size=chunk_size)
    for chunk in base_chunks:
        if "উদাহরণ" in chunk.original_text or "example" in chunk.original_text.lower():
            chunk.chunk_type = "example"
    return base_chunks


def table_aware_chunking(
    pages: list[ParsedPage],
    metadata: ChunkingMetadata,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[ChunkRecord]:
    base_chunks = section_aware_chunking(pages, metadata, chunk_size=chunk_size)
    for chunk in base_chunks:
        matching_page = next((page for page in pages if page.page_no == chunk.page_no), None)
        if matching_page and matching_page.is_table_like:
            chunk.chunk_type = "table"
    return base_chunks


def chunk_pages(
    pages: list[ParsedPage],
    *,
    doc_id: str,
    doc_title: str,
    doc_type: str,
    authority_level: str,
    chunking_mode: str = "section_aware",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[ChunkRecord]:
    metadata = ChunkingMetadata(
        doc_id=doc_id,
        doc_title=doc_title,
        doc_type=doc_type,
        authority_level=authority_level,
    )
    strategies = {
        "naive_fixed_chunking": naive_fixed_chunking,
        "naive": naive_fixed_chunking,
        "section_aware_chunking": section_aware_chunking,
        "section_aware": section_aware_chunking,
        "example_aware_chunking": example_aware_chunking,
        "example_aware": example_aware_chunking,
        "table_aware_chunking": table_aware_chunking,
        "table_aware": table_aware_chunking,
    }
    chunker = strategies.get(chunking_mode, section_aware_chunking)
    raw_chunks = chunker(pages, metadata, chunk_size=chunk_size)
    return [chunk for chunk in raw_chunks if not _is_low_value_chunk_text(chunk.normalized_text)]
