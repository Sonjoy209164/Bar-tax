import argparse
import csv
import json
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and optionally execute OCR-enabled Pilot14 ingestion commands. "
            "Outputs OCR PDFs, per-document chunk JSONL, logs, and command provenance."
        )
    )
    parser.add_argument(
        "--manifest",
        default="data/metadata/corpus_manifest_btax14.csv",
        help="Pilot14 corpus manifest CSV.",
    )
    parser.add_argument(
        "--pdf-dir",
        default="data/raw/btax14/pdfs",
        help="Directory containing stable btax14 PDF files.",
    )
    parser.add_argument(
        "--ocr-pdf-dir",
        default="data/processed/btax14/ocr_pdfs",
        help="Directory where OCR PDF outputs will be written.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed/btax14/ocr_per_doc",
        help="Directory where OCR-parsed per-document JSONL outputs will be written.",
    )
    parser.add_argument(
        "--results-dir",
        default="results/pilot14",
        help="Directory where command logs and summaries will be written.",
    )
    parser.add_argument(
        "--doc-ids",
        nargs="*",
        default=None,
        help="Optional subset of doc ids. Defaults to all manifest rows.",
    )
    parser.add_argument(
        "--ocr-language",
        default="ben+eng",
        help="OCRmyPDF/Tesseract language string.",
    )
    parser.add_argument(
        "--chunking-mode",
        default="section_aware",
        help="Chunking mode passed to scripts/ingest_pdf.py.",
    )
    parser.add_argument(
        "--ocr-skip-force",
        action="store_true",
        help="Pass --ocr-skip-force to ingest_pdf.py instead of force OCR.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete existing OCR PDFs, OCR JSONL outputs, and logs before rerunning.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute commands. Without this flag, only command files are written.",
    )
    return parser


def read_manifest(path: Path, doc_ids: set[str] | None) -> list[dict[str, str]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if doc_ids is None:
        return rows
    selected_rows = [row for row in rows if row["doc_id"] in doc_ids]
    missing = sorted(doc_ids - {row["doc_id"] for row in selected_rows})
    if missing:
        raise SystemExit(f"Unknown doc ids in manifest: {', '.join(missing)}")
    return selected_rows


def build_ingest_command(
    *,
    row: dict[str, str],
    pdf_dir: Path,
    ocr_pdf_dir: Path,
    output_dir: Path,
    ocr_language: str,
    chunking_mode: str,
    ocr_skip_force: bool,
) -> tuple[list[str], Path, Path]:
    doc_id = row["doc_id"].strip()
    pdf_path = pdf_dir / row["file_name"].strip()
    ocr_pdf_path = ocr_pdf_dir / f"{doc_id}.ocr.pdf"
    output_path = output_dir / f"{doc_id}.jsonl"
    command = [
        ".venv/bin/python",
        "scripts/ingest_pdf.py",
        "--input",
        str(pdf_path),
        "--doc-id",
        doc_id,
        "--doc-title",
        row.get("title", "").strip() or doc_id,
        "--doc-type",
        row.get("authority_type", "").strip() or "other",
        "--authority-level",
        "national",
        "--chunking-mode",
        chunking_mode,
        "--ocr-enabled",
        "--ocr-language",
        ocr_language,
        "--ocr-output-pdf",
        str(ocr_pdf_path),
        "--output",
        str(output_path),
    ]
    if ocr_skip_force:
        command.append("--ocr-skip-force")
    return command, ocr_pdf_path, output_path


def count_jsonl_rows(path: Path) -> int | None:
    if not path.exists():
        return None
    return sum(1 for line in path.open(encoding="utf-8") if line.strip())


def remove_if_requested(paths: list[Path], *, overwrite: bool) -> None:
    if not overwrite:
        return
    for path in paths:
        if path.exists():
            path.unlink()


def write_command_files(
    *,
    command_records: list[dict[str, object]],
    results_dir: Path,
) -> tuple[Path, Path]:
    shell_path = results_dir / "pilot14_ocr_ingest_commands.sh"
    jsonl_path = results_dir / "pilot14_ocr_ingest_commands.jsonl"

    with shell_path.open("w", encoding="utf-8") as handle:
        handle.write("#!/usr/bin/env bash\n")
        handle.write("set -euo pipefail\n\n")
        handle.write('cd "/home/sonjoy/Bar tax/bangla-tax-rag"\n\n')
        for record in command_records:
            command = record["command"]
            if not isinstance(command, list):
                continue
            handle.write("# " + str(record["doc_id"]) + "\n")
            handle.write(" ".join(shlex.quote(part) for part in command) + "\n\n")

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in command_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return shell_path, jsonl_path


def main() -> None:
    args = build_argument_parser().parse_args()
    manifest_path = Path(args.manifest)
    pdf_dir = Path(args.pdf_dir)
    ocr_pdf_dir = Path(args.ocr_pdf_dir)
    output_dir = Path(args.output_dir)
    results_dir = Path(args.results_dir)
    stdout_dir = results_dir / "ocr_ingest_stdout"
    stderr_dir = results_dir / "ocr_ingest_stderr"

    for directory in [ocr_pdf_dir, output_dir, results_dir, stdout_dir, stderr_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    doc_ids = set(args.doc_ids) if args.doc_ids else None
    rows = read_manifest(manifest_path, doc_ids)
    run_started_at = datetime.now(UTC).isoformat()

    command_records: list[dict[str, object]] = []
    for row in rows:
        command, ocr_pdf_path, output_path = build_ingest_command(
            row=row,
            pdf_dir=pdf_dir,
            ocr_pdf_dir=ocr_pdf_dir,
            output_dir=output_dir,
            ocr_language=args.ocr_language,
            chunking_mode=args.chunking_mode,
            ocr_skip_force=args.ocr_skip_force,
        )
        doc_id = row["doc_id"].strip()
        command_records.append(
            {
                "doc_id": doc_id,
                "file_name": row["file_name"],
                "input_pdf": str(pdf_dir / row["file_name"].strip()),
                "ocr_pdf": str(ocr_pdf_path),
                "output_jsonl": str(output_path),
                "stdout_log": str(stdout_dir / f"{doc_id}.log"),
                "stderr_log": str(stderr_dir / f"{doc_id}.log"),
                "ocr_language": args.ocr_language,
                "chunking_mode": args.chunking_mode,
                "ocr_force": not args.ocr_skip_force,
                "command": command,
                "run_started_at": run_started_at,
            }
        )

    shell_path, jsonl_path = write_command_files(command_records=command_records, results_dir=results_dir)
    print(f"Wrote shell commands to {shell_path}")
    print(f"Wrote command metadata to {jsonl_path}")

    execution_results: list[dict[str, object]] = []
    if args.execute:
        for record in command_records:
            doc_id = str(record["doc_id"])
            command = record["command"]
            if not isinstance(command, list):
                raise SystemExit(f"Invalid command for {doc_id}")
            input_pdf = Path(str(record["input_pdf"]))
            ocr_pdf = Path(str(record["ocr_pdf"]))
            output_jsonl = Path(str(record["output_jsonl"]))
            stdout_log = Path(str(record["stdout_log"]))
            stderr_log = Path(str(record["stderr_log"]))

            if not input_pdf.exists():
                raise FileNotFoundError(input_pdf)
            remove_if_requested([ocr_pdf, output_jsonl, stdout_log, stderr_log], overwrite=args.overwrite)

            print(f"Running OCR ingest for {doc_id}")
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            stdout_log.write_text(completed.stdout, encoding="utf-8")
            stderr_log.write_text(completed.stderr, encoding="utf-8")

            result = {
                "doc_id": doc_id,
                "returncode": completed.returncode,
                "ocr_pdf": str(ocr_pdf),
                "output_jsonl": str(output_jsonl),
                "chunk_count": count_jsonl_rows(output_jsonl),
                "stdout_log": str(stdout_log),
                "stderr_log": str(stderr_log),
                "completed_at": datetime.now(UTC).isoformat(),
            }
            execution_results.append(result)
            print(json.dumps(result, ensure_ascii=False))
            if completed.returncode != 0:
                summary_path = results_dir / "pilot14_ocr_ingest_summary.json"
                summary_path.write_text(json.dumps(execution_results, ensure_ascii=False, indent=2), encoding="utf-8")
                raise SystemExit(completed.returncode)
    else:
        print("Dry run only. Re-run with --execute to OCR and parse PDFs.")

    summary = {
        "execute": args.execute,
        "overwrite": args.overwrite,
        "manifest": str(manifest_path),
        "pdf_dir": str(pdf_dir),
        "ocr_pdf_dir": str(ocr_pdf_dir),
        "output_dir": str(output_dir),
        "results_dir": str(results_dir),
        "doc_count": len(command_records),
        "run_started_at": run_started_at,
        "run_finished_at": datetime.now(UTC).isoformat(),
        "commands_shell": str(shell_path),
        "commands_jsonl": str(jsonl_path),
        "results": execution_results,
    }
    summary_path = results_dir / "pilot14_ocr_ingest_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
