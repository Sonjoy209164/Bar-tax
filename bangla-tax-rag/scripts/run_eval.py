import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging, get_logger
from app.core.utils import ensure_directory
from app.eval.metrics import evaluate_dataset_file


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run placeholder local evaluation against a JSONL dataset.")
    parser.add_argument("--dataset", required=True, dest="dataset_path", help="Path to evaluation dataset JSONL.")
    parser.add_argument("--output-dir", default="results/eval", dest="output_dir", help="Directory for evaluation outputs.")
    return parser


def main() -> None:
    configure_logging()
    logger = get_logger(__name__)
    args = build_argument_parser().parse_args()
    metrics = evaluate_dataset_file(args.dataset_path)
    output_dir = ensure_directory(args.output_dir)
    output_path = output_dir / "evaluation_summary.json"
    output_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Evaluation complete", extra={"dataset_path": args.dataset_path, "output_path": str(output_path)})
    print(f"Evaluation complete. Summary written to {output_path}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
