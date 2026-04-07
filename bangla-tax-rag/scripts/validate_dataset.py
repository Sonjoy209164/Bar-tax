import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging, get_logger
from app.eval.dataset_builder import validate_annotated_dataset


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an annotated benchmark dataset against chunk JSONL.")
    parser.add_argument("--dataset", required=True, dest="dataset_path", help="Path to annotated dataset JSONL.")
    parser.add_argument("--chunks", required=True, dest="chunk_jsonl_path", help="Path to source chunk JSONL.")
    return parser


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    args = build_argument_parser().parse_args()
    report = validate_annotated_dataset(args.dataset_path, args.chunk_jsonl_path)
    logger.info("Dataset validation complete", extra={"valid": report.valid, "dataset_path": args.dataset_path})
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.valid else 1)


if __name__ == "__main__":
    main()
