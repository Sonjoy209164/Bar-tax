from collections.abc import Iterable
from dataclasses import dataclass

from app.core.schemas import ChunkRecord, ParsedPage
from app.core.utils import extract_cross_references, extract_section_ids, normalize_text


DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 120


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
    section_markers = extract_section_ids(chunk_text)
    section_id = next(
        (marker for marker in section_markers if marker and marker[0].isdigit()),
        page.section_markers[0] if page.section_markers else None,
    )
    subsection_id = next(
        (marker for marker in section_markers if "." in marker),
        None,
    )
    appendix_id = next(
        (marker for marker in page.section_markers if marker.lower().startswith("পরিশিষ্ট")),
        None,
    )
    tax_year = page.tax_years[0] if page.tax_years else None
    effective_start, effective_end = _derive_effective_dates(tax_year)
    sro_id = page.sro_ids[0] if page.sro_ids else None
    normalized_chunk_text = normalize_text(chunk_text)
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
        original_text=chunk_text.strip(),
        normalized_text=normalized_chunk_text,
        cross_refs=extract_cross_references(chunk_text),
    )


def _iter_page_blocks(page: ParsedPage) -> Iterable[tuple[str, list[str], str]]:
    lines = [line.strip() for line in page.raw_text.splitlines() if line.strip()]
    if not lines:
        return
    active_heading_path = list(page.headings[:1])
    current_lines: list[str] = []
    current_type = "text"
    for line in lines:
        if line in page.headings:
            if current_lines:
                yield "\n".join(current_lines), list(active_heading_path), current_type
                current_lines = []
            active_heading_path = active_heading_path + [line] if line not in active_heading_path else list(active_heading_path)
            current_type = "section"
            continue
        if "উদাহরণ" in line or "example" in line.lower() or page.is_example:
            if current_lines:
                yield "\n".join(current_lines), list(active_heading_path), current_type
                current_lines = []
            current_type = "example"
        elif page.is_table_like:
            current_type = "table"
        elif page.is_appendix:
            current_type = "appendix"
        current_lines.append(line)
    if current_lines:
        yield "\n".join(current_lines), list(active_heading_path), current_type


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
    for page in pages:
        for block_text, heading_path, chunk_type in _iter_page_blocks(page):
            for piece in _split_text_with_overlap(block_text, chunk_size):
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
    return chunker(pages, metadata, chunk_size=chunk_size)
