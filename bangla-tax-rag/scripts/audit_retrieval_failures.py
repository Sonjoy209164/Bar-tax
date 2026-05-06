import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("results/pilot14/retrieval_eval_150.json")
DEFAULT_OUTPUT_JSON = Path("results/pilot14/retrieval_failure_audit_150.json")
DEFAULT_OUTPUT_MD = Path("results/pilot14/retrieval_failure_audit_150.md")
FAILURE_CATEGORIES = (
    "hit_top5",
    "same_page_wrong_chunk",
    "adjacent_page_near_miss",
    "same_doc_wrong_section",
    "wrong_doc_top5",
    "no_results",
    "wrong_year_top1",
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit retrieval failures from a Pilot14 retrieval eval JSON.")
    parser.add_argument("--input-json", default=str(DEFAULT_INPUT), help="Retrieval evaluation JSON.")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON), help="Failure audit JSON output.")
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD), help="Failure audit Markdown output.")
    parser.add_argument("--priority-mode", default="hybrid", help="Mode used for the priority miss table.")
    parser.add_argument("--max-priority-misses", type=int, default=25, help="Maximum priority misses to show in Markdown.")
    return parser


def classify_row(row: dict[str, Any]) -> str:
    if row.get("gold_chunk_in_top_5"):
        return "hit_top5"
    if row.get("wrong_year"):
        return "wrong_year_top1"
    top_hits = row.get("top_hits") or []
    if not top_hits:
        return "no_results"
    if not row.get("doc_hit_at_5"):
        return "wrong_doc_top5"
    if row.get("page_hit_at_5"):
        return "same_page_wrong_chunk"
    if row.get("adjacent_page_hit_at_5"):
        return "adjacent_page_near_miss"
    return "same_doc_wrong_section"


def summarize_mode_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {category: 0 for category in FAILURE_CATEGORIES}
    for row in rows:
        if not row.get("evaluated_for_evidence_metrics"):
            continue
        counts[classify_row(row)] += 1
    return counts


def build_misses(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    misses: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("evaluated_for_evidence_metrics"):
            continue
        category = classify_row(row)
        if category == "hit_top5":
            continue
        misses.append(
            {
                "question_id": row["question_id"],
                "question_type": row["question_type"],
                "category": category,
                "expected_chunk_ids": row.get("expected_chunk_ids") or [],
                "top_5_chunk_ids": [hit["chunk_id"] for hit in (row.get("top_hits") or [])[:5]],
                "doc_hit_at_5": row.get("doc_hit_at_5"),
                "page_hit_at_5": row.get("page_hit_at_5"),
                "adjacent_page_hit_at_5": row.get("adjacent_page_hit_at_5"),
                "expected_tax_year": row.get("expected_tax_year"),
                "top_hit_tax_year": row.get("top_hit_tax_year"),
                "question_text": row["question_text"],
            }
        )
    return misses


def metric(summary: dict[str, Any], name: str) -> float:
    return float(summary.get("metrics", {}).get(name, 0.0))


def markdown_table_row(mode: str, summary: dict[str, Any]) -> str:
    return (
        f"| {mode} | {metric(summary, 'evidence_hit_at_1'):.4f} "
        f"| {metric(summary, 'evidence_hit_at_3'):.4f} "
        f"| {metric(summary, 'evidence_hit_at_5'):.4f} "
        f"| {metric(summary, 'mrr'):.4f} "
        f"| {metric(summary, 'tax_year_accuracy_top1'):.4f} "
        f"| {metric(summary, 'wrong_year_retrieval_rate_top1'):.4f} "
        f"| {metric(summary, 'doc_hit_at_5'):.4f} "
        f"| {metric(summary, 'page_hit_at_5'):.4f} "
        f"| {metric(summary, 'adjacent_page_hit_at_5'):.4f} |"
    )


def write_markdown(
    *,
    source_eval: Path,
    mode_summaries: dict[str, Any],
    failure_counts: dict[str, dict[str, int]],
    misses: dict[str, list[dict[str, Any]]],
    priority_mode: str,
    max_priority_misses: int,
    output_md: Path,
) -> None:
    lines = [
        "# Pilot14-150 Retrieval Failure Audit",
        "",
        f"Source eval: `{source_eval}`",
        "",
        "## Summary",
        "",
        "| mode | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Wrong-Year@1 | Doc@5 | Page@5 | Adjacent@5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, summary in mode_summaries.items():
        lines.append(markdown_table_row(mode, summary))

    lines.extend(
        [
            "",
            "## Failure Class Counts",
            "",
            "| mode | hit_top5 | same_page_wrong_chunk | adjacent_page_near_miss | same_doc_wrong_section | wrong_doc_top5 | no_results | wrong_year_top1 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for mode, counts in failure_counts.items():
        lines.append(
            f"| {mode} | {counts['hit_top5']} | {counts['same_page_wrong_chunk']} "
            f"| {counts['adjacent_page_near_miss']} | {counts['same_doc_wrong_section']} "
            f"| {counts['wrong_doc_top5']} | {counts['no_results']} | {counts['wrong_year_top1']} |"
        )

    priority_misses = misses.get(priority_mode, [])[:max_priority_misses]
    lines.extend(
        [
            "",
            f"## {priority_mode.title()} Remaining Priority Misses",
            "",
            "These are strict Hit@5 misses after the Pilot14-150 expansion and temporal chunk-year repair. Most remaining misses are evidence locality errors: right document, adjacent page, or same legal unit but not the exact gold chunk.",
            "",
            "| question_id | type | category | expected | top_5 | question |",
            "|---|---|---|---|---|---|",
        ]
    )
    for miss in priority_misses:
        expected = ", ".join(f"`{chunk_id}`" for chunk_id in miss["expected_chunk_ids"]) or "none"
        top_5 = ", ".join(f"`{chunk_id}`" for chunk_id in miss["top_5_chunk_ids"]) or "none"
        question = str(miss["question_text"]).replace("|", "\\|")
        lines.append(
            f"| `{miss['question_id']}` | {miss['question_type']} | {miss['category']} | {expected} | {top_5} | {question} |"
        )

    hybrid_summary = mode_summaries.get(priority_mode, {})
    lines.extend(
        [
            "",
            "## Readout",
            "",
            f"- {priority_mode.title()} strict Evidence Hit@5: {metric(hybrid_summary, 'evidence_hit_at_5'):.4f}.",
            f"- Tax-year accuracy: {metric(hybrid_summary, 'tax_year_accuracy_top1'):.4f}; wrong-year top hits: {metric(hybrid_summary, 'wrong_year_retrieval_rate_top1'):.4f}.",
            "- The 2026-2027 rows validate that explicit chunk tax-year metadata must override document-title tax year when the heading/text marks a future tax year.",
            "- Evaluation runtime is now high enough that query embedding caching or batched dense evaluation should be a near-term engineering fix.",
        ]
    )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = build_argument_parser().parse_args()
    input_json = Path(args.input_json)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    eval_payload = json.loads(input_json.read_text(encoding="utf-8"))

    rows_by_mode: dict[str, list[dict[str, Any]]] = {mode: [] for mode in eval_payload["modes"]}
    for row in eval_payload["rows"]:
        rows_by_mode.setdefault(row["mode"], []).append(row)

    failure_counts = {mode: summarize_mode_rows(rows) for mode, rows in rows_by_mode.items()}
    misses = {mode: build_misses(rows) for mode, rows in rows_by_mode.items()}
    audit_payload = {
        "source_eval": str(input_json),
        "mode_summaries": eval_payload["mode_summaries"],
        "failure_class_counts": failure_counts,
        "misses": misses,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(
        source_eval=input_json,
        mode_summaries=eval_payload["mode_summaries"],
        failure_counts=failure_counts,
        misses=misses,
        priority_mode=args.priority_mode,
        max_priority_misses=args.max_priority_misses,
        output_md=output_md,
    )
    print(f"Wrote {output_json}")
    print(f"Wrote {output_md}")


if __name__ == "__main__":
    main()
