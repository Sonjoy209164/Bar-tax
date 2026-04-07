import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging, get_logger
from app.retrieval.dense import build_dense_index_artifacts


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build dense-overlap placeholder index artifacts from chunk JSONL.")
    parser.add_argument("--input", required=True, dest="input_path", help="Path to chunk JSONL file.")
    parser.add_argument("--output", default="indexes/dense", dest="output_dir", help="Output directory for dense index artifacts.")
    return parser


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    args = build_argument_parser().parse_args()
    output_path, chunk_count = build_dense_index_artifacts(args.input_path, args.output_dir)
    logger.info("Dense index built", extra={"output_dir": str(output_path), "chunk_count": chunk_count})
    print(f"Built dense index with {chunk_count} chunks at {output_path}")


if __name__ == "__main__":
    main()
