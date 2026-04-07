import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging, get_logger
from app.eval.dataset_builder import build_annotation_candidates_from_chunks, write_annotation_candidates
from app.retrieval.sparse import load_chunk_records_from_jsonl


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate human-annotation candidates from chunk JSONL.")
    parser.add_argument("--chunks", required=True, dest="chunk_jsonl_path", help="Path to chunk JSONL file.")
    parser.add_argument("--output", required=True, dest="output_path", help="Output JSONL path for annotation candidates.")
    return parser


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    args = build_argument_parser().parse_args()
    chunk_records = load_chunk_records_from_jsonl(args.chunk_jsonl_path)
    candidates = build_annotation_candidates_from_chunks(chunk_records)
    output_path = write_annotation_candidates(candidates, args.output_path)
    logger.info("Annotation candidates generated", extra={"count": len(candidates), "output_path": str(output_path)})
    print(f"Generated {len(candidates)} annotation candidates at {output_path}")


if __name__ == "__main__":
    main()
