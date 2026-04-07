import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging, get_logger
from app.eval.annotation import merge_annotation_files, write_merged_annotations


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge one or more annotated JSONL files into a deduplicated final dataset.")
    parser.add_argument("--inputs", nargs="+", required=True, help="One or more annotated JSONL files.")
    parser.add_argument("--output", required=True, help="Output JSONL path for the merged dataset.")
    return parser


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    args = build_argument_parser().parse_args()
    merged_rows = merge_annotation_files(args.inputs)
    output_path = write_merged_annotations(merged_rows, args.output)
    logger.info("Merged annotation dataset written", extra={"row_count": len(merged_rows), "output_path": str(output_path)})
    print(f"Merged {len(merged_rows)} annotated rows into {output_path}")


if __name__ == "__main__":
    main()
