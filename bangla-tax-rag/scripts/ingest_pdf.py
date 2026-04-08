import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.utils import ensure_directory
from app.ingest.chunker import chunk_pages
from app.ingest.parser import parse_document, prepare_pdf_for_ingestion


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse a PDF and emit JSONL chunk records.")
    parser.add_argument("--input", required=True, dest="input_path", help="Path to input PDF file.")
    parser.add_argument("--doc-id", required=True, help="Document identifier.")
    parser.add_argument("--doc-title", required=True, help="Human-readable document title.")
    parser.add_argument("--doc-type", required=True, help="Document type label.")
    parser.add_argument("--authority-level", required=True, help="Authority level label.")
    parser.add_argument("--chunking-mode", default="section_aware", help="Chunking mode to apply.")
    parser.add_argument("--output", required=True, help="Output JSONL path.")
    parser.add_argument("--ocr-enabled", action="store_true", help="Run OCRmyPDF before parsing.")
    parser.add_argument("--ocr-language", default="ben+eng", help="OCR language pack string for OCRmyPDF.")
    parser.add_argument("--ocr-skip-force", action="store_true", help="Use --skip-text instead of --force-ocr.")
    parser.add_argument("--ocr-output-pdf", default=None, help="Optional path for the OCR-processed PDF.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    parse_input_path, ocr_output_path = prepare_pdf_for_ingestion(
        args.input_path,
        ocr_enabled=args.ocr_enabled,
        ocr_language=args.ocr_language,
        ocr_force=not args.ocr_skip_force,
        ocr_output_pdf_path=args.ocr_output_pdf,
    )
    parsed_pages = parse_document(str(parse_input_path))
    chunk_records = chunk_pages(
        parsed_pages,
        doc_id=args.doc_id,
        doc_title=args.doc_title,
        doc_type=args.doc_type,
        authority_level=args.authority_level,
        chunking_mode=args.chunking_mode,
    )
    output_path = Path(args.output)
    ensure_directory(str(output_path.parent))
    with output_path.open("w", encoding="utf-8") as handle:
        for chunk_record in chunk_records:
            handle.write(json.dumps(chunk_record.model_dump(), ensure_ascii=False) + "\n")
    if ocr_output_path is not None:
        print(f"OCR PDF written to {ocr_output_path}")
    print(f"Wrote {len(chunk_records)} chunks to {output_path}")


if __name__ == "__main__":
    main()
