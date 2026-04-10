import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging, get_logger
from app.retrieval.dense import build_dense_index_artifacts


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build dense index artifacts from chunk JSONL.")
    parser.add_argument("--input", required=True, dest="input_path", help="Path to chunk JSONL file.")
    parser.add_argument("--output", default="indexes/dense", dest="output_dir", help="Output directory for dense index artifacts.")
    parser.add_argument(
        "--provider",
        default=None,
        choices=["mock", "transformers"],
        help="Dense embedding provider. Defaults to the configured runtime setting.",
    )
    parser.add_argument(
        "--model-name",
        default=None,
        dest="model_name",
        help="Embedding model name to use when provider=transformers.",
    )
    parser.add_argument(
        "--no-faiss",
        action="store_true",
        help="Disable FAISS index materialization and keep numpy-only dense search artifacts.",
    )
    return parser


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    args = build_argument_parser().parse_args()
    output_path, chunk_count = build_dense_index_artifacts(
        args.input_path,
        args.output_dir,
        provider=args.provider,
        model_name=args.model_name,
        use_faiss=not args.no_faiss,
    )
    logger.info("Dense index built", extra={"output_dir": str(output_path), "chunk_count": chunk_count})
    print(f"Built dense index with {chunk_count} chunks at {output_path}")


if __name__ == "__main__":
    main()
