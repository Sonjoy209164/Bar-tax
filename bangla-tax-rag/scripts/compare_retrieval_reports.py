import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_JSON = Path("results/pilot14/retrieval_eval_150_taxtrail_comparison.json")
DEFAULT_OUTPUT_MD = Path("results/pilot14/retrieval_eval_150_taxtrail_comparison.md")
MODE_ORDER = ("sparse", "dense", "hybrid", "taxtrail")


def load_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect_mode_summaries(report_paths: list[str | Path]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for report_path in report_paths:
        report = load_report(report_path)
        for mode, summary in report.get("mode_summaries", {}).items():
            summaries[mode] = summary
    return summaries


def ordered_modes(summaries: dict[str, dict[str, Any]]) -> list[str]:
    known = [mode for mode in MODE_ORDER if mode in summaries]
    unknown = sorted(mode for mode in summaries if mode not in MODE_ORDER)
    return [*known, *unknown]


def metric(summary: dict[str, Any], name: str) -> float:
    return float(summary.get("metrics", {}).get(name, 0.0))


def build_comparison_report(report_paths: list[str | Path]) -> dict[str, Any]:
    summaries = collect_mode_summaries(report_paths)
    modes = ordered_modes(summaries)
    hybrid_hit_at_5 = metric(summaries["hybrid"], "evidence_hit_at_5") if "hybrid" in summaries else 0.0
    rows = []
    for mode in modes:
        summary = summaries[mode]
        rows.append(
            {
                "mode": mode,
                "questions": summary["total_questions"],
                "answerable": summary["answerable_evidence_questions"],
                "hit_at_1": metric(summary, "evidence_hit_at_1"),
                "hit_at_3": metric(summary, "evidence_hit_at_3"),
                "hit_at_5": metric(summary, "evidence_hit_at_5"),
                "mrr": metric(summary, "mrr"),
                "tax_year_accuracy_top1": metric(summary, "tax_year_accuracy_top1"),
                "wrong_year_rate_top1": metric(summary, "wrong_year_retrieval_rate_top1"),
                "doc_hit_at_5": metric(summary, "doc_hit_at_5"),
                "page_hit_at_5": metric(summary, "page_hit_at_5"),
                "delta_hit_at_5_vs_hybrid": round(metric(summary, "evidence_hit_at_5") - hybrid_hit_at_5, 4)
                if "hybrid" in summaries
                else None,
            }
        )
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_reports": [str(path) for path in report_paths],
        "rows": rows,
    }


def write_json_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_markdown_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Pilot14 v0.1 Retrieval Method Comparison",
        "",
        f"Date: {report['created_at']}",
        "",
        "Source reports:",
        "",
        *[f"- `{source_report}`" for source_report in report["source_reports"]],
        "",
        "## Summary",
        "",
        "| mode | questions | answerable | Hit@1 | Hit@3 | Hit@5 | delta Hit@5 vs hybrid | MRR | Tax-Year Acc@1 | Wrong-Year@1 | Doc@5 | Page@5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        delta = row["delta_hit_at_5_vs_hybrid"]
        delta_text = "n/a" if delta is None else f"{delta:+.4f}"
        lines.append(
            "| "
            + " | ".join(
                [
                    row["mode"],
                    str(row["questions"]),
                    str(row["answerable"]),
                    f"{row['hit_at_1']:.4f}",
                    f"{row['hit_at_3']:.4f}",
                    f"{row['hit_at_5']:.4f}",
                    delta_text,
                    f"{row['mrr']:.4f}",
                    f"{row['tax_year_accuracy_top1']:.4f}",
                    f"{row['wrong_year_rate_top1']:.4f}",
                    f"{row['doc_hit_at_5']:.4f}",
                    f"{row['page_hit_at_5']:.4f}",
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare retrieval eval reports across sparse/dense/hybrid/TaxTrail.")
    parser.add_argument("--reports", nargs="+", required=True, help="Retrieval eval JSON reports to merge.")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON), help="Comparison JSON output path.")
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD), help="Comparison Markdown output path.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    report = build_comparison_report(args.reports)
    json_path = write_json_report(report, args.output_json)
    markdown_path = write_markdown_report(report, args.output_md)
    print(f"Retrieval comparison written to {json_path} and {markdown_path}")
    print(json.dumps(report["rows"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
