import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging, get_logger
from app.retrieval.sparse import build_sparse_index, load_chunk_records_from_jsonl, save_sparse_index


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a sparse BM25 index from chunk JSONL.")
    parser.add_argument("--input", required=True, dest="input_path", help="Path to chunk JSONL input.")
    parser.add_argument("--output", default="indexes/sparse", dest="output_dir", help="Output directory for sparse index artifacts.")
    return parser


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    args = build_argument_parser().parse_args()
    chunk_records = load_chunk_records_from_jsonl(args.input_path)
    sparse_index = build_sparse_index(chunk_records)
    output_path = save_sparse_index(sparse_index, args.output_dir)
    logger.info("Sparse index built", extra={"chunk_count": len(chunk_records), "output_dir": str(output_path)})
    print(f"Built sparse index with {len(chunk_records)} chunks at {output_path}")


if __name__ == "__main__":
    main()
