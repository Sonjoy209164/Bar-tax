import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.utils import ensure_directory
from app.ingest.chunker import chunk_pages
from app.ingest.parser import parse_document


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse a PDF and emit JSONL chunk records.")
    parser.add_argument("--input", required=True, dest="input_path", help="Path to input PDF file.")
    parser.add_argument("--doc-id", required=True, help="Document identifier.")
    parser.add_argument("--doc-title", required=True, help="Human-readable document title.")
    parser.add_argument("--doc-type", required=True, help="Document type label.")
    parser.add_argument("--authority-level", required=True, help="Authority level label.")
    parser.add_argument("--chunking-mode", default="section_aware", help="Chunking mode to apply.")
    parser.add_argument("--output", required=True, help="Output JSONL path.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    parsed_pages = parse_document(args.input_path)
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
    print(f"Wrote {len(chunk_records)} chunks to {output_path}")


if __name__ == "__main__":
    main()
