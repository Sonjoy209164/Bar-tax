import argparse
import sys
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging
from app.core.utils import ensure_directory
from app.retrieval.sparse import load_sparse_index, search_sparse_index

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 48
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)
BODY_FONT = "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf"
BOLD_FONT = "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Save sparse retrieval results as a formatted PDF.")
    parser.add_argument("--index-dir", default="indexes/sparse")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", default="results/demo_query_response.pdf")
    return parser


def add_page(document: fitz.Document) -> tuple[fitz.Page, float]:
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_font(fontname="bangla_regular", fontfile=BODY_FONT)
    page.insert_font(fontname="bangla_bold", fontfile=BOLD_FONT)
    return page, float(MARGIN)


def write_block(
    document: fitz.Document,
    page: fitz.Page,
    y_position: float,
    text: str,
    *,
    fontname: str,
    fontsize: float,
    color: tuple[float, float, float] = (0, 0, 0),
    spacing_after: float = 10,
) -> tuple[fitz.Page, float]:
    estimated_height = max(28, (text.count("\n") + max(1, len(text) // 70) + 1) * (fontsize + 4))
    if y_position + estimated_height > PAGE_HEIGHT - MARGIN:
        page, y_position = add_page(document)
    text_rect = fitz.Rect(MARGIN, y_position, MARGIN + CONTENT_WIDTH, PAGE_HEIGHT - MARGIN)
    used_height = page.insert_textbox(
        text_rect,
        text,
        fontname=fontname,
        fontsize=fontsize,
        color=color,
        align=fitz.TEXT_ALIGN_LEFT,
        lineheight=1.3,
    )
    if used_height < 0:
        page, y_position = add_page(document)
        text_rect = fitz.Rect(MARGIN, y_position, MARGIN + CONTENT_WIDTH, PAGE_HEIGHT - MARGIN)
        used_height = page.insert_textbox(
            text_rect,
            text,
            fontname=fontname,
            fontsize=fontsize,
            color=color,
            align=fitz.TEXT_ALIGN_LEFT,
            lineheight=1.3,
        )
    next_y = y_position + max(estimated_height, used_height if used_height > 0 else estimated_height) + spacing_after
    return page, next_y


def main() -> None:
    configure_logging()
    args = build_argument_parser().parse_args()
    index = load_sparse_index(args.index_dir)
    response = search_sparse_index(query=args.query, index=index, top_k=args.top_k)

    document = fitz.open()
    page, y_position = add_page(document)

    page, y_position = write_block(
        document,
        page,
        y_position,
        "Bangla Tax RAG Query Results",
        fontname="bangla_bold",
        fontsize=20,
        color=(0.08, 0.17, 0.34),
        spacing_after=14,
    )
    page, y_position = write_block(
        document,
        page,
        y_position,
        f"Query:\n{response.query}",
        fontname="bangla_bold",
        fontsize=12,
        spacing_after=6,
    )
    page, y_position = write_block(
        document,
        page,
        y_position,
        f"Normalized Query:\n{response.signals.normalized_query}",
        fontname="bangla_regular",
        fontsize=11,
        color=(0.2, 0.2, 0.2),
        spacing_after=12,
    )

    if not response.hits:
        page, y_position = write_block(
            document,
            page,
            y_position,
            "No hits were found for this query.",
            fontname="bangla_regular",
            fontsize=12,
        )
    else:
        for rank, hit in enumerate(response.hits, start=1):
            heading_text = f"Result {rank} | Score {hit.score}"
            metadata_lines = [
                f"Document: {hit.doc_title}",
                f"Chunk ID: {hit.chunk_id}",
                f"Page: {hit.page_no} | Authority: {hit.authority_level} | Tax Year: {hit.tax_year or '-'}",
                f"Section: {hit.section_id or '-'} | Subsection: {hit.subsection_id or '-'} | Chunk Type: {hit.chunk_type}",
                f"Headings: {' > '.join(hit.heading_path) if hit.heading_path else '-'}",
            ]
            page, y_position = write_block(
                document,
                page,
                y_position,
                heading_text,
                fontname="bangla_bold",
                fontsize=14,
                color=(0.12, 0.32, 0.22),
                spacing_after=6,
            )
            page, y_position = write_block(
                document,
                page,
                y_position,
                "\n".join(metadata_lines),
                fontname="bangla_regular",
                fontsize=10,
                spacing_after=8,
            )
            page.draw_line(
                fitz.Point(MARGIN, y_position - 4),
                fitz.Point(PAGE_WIDTH - MARGIN, y_position - 4),
                color=(0.75, 0.8, 0.85),
                width=0.8,
            )
            page, y_position = write_block(
                document,
                page,
                y_position,
                hit.original_text,
                fontname="bangla_regular",
                fontsize=11,
                spacing_after=18,
            )

    output_path = Path(args.output)
    ensure_directory(str(output_path.parent))
    document.save(output_path)
    document.close()
    print(f"Saved formatted PDF to {output_path}")


if __name__ == "__main__":
    main()
