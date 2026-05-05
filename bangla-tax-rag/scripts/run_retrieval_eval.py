import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import configure_logging, get_logger
from app.core.schemas import RetrievalHit
from app.core.utils import preprocess_query
from app.retrieval.dense import dense_search, load_dense_index_metadata
from app.retrieval.hybrid import run_hybrid_retrieval
from app.retrieval.sparse import load_sparse_index, search_sparse_index


DEFAULT_DATASET_PATH = Path("data/btaxbench/pilot14/pilot14_50.jsonl")
DEFAULT_SPARSE_INDEX_DIR = Path("indexes/pilot14/sparse")
DEFAULT_DENSE_INDEX_DIR = Path("indexes/pilot14/dense")
DEFAULT_OUTPUT_JSON = Path("results/pilot14/retrieval_eval_50.json")
DEFAULT_OUTPUT_MD = Path("results/pilot14/retrieval_eval_50.md")
DEFAULT_MODES = ("sparse", "dense", "hybrid")
TOP_K_VALUES = (1, 3, 5)
CHUNK_ID_PAGE_PATTERN = re.compile(r"^(?P<doc_id>.+)-p(?P<page>\d+)-c\d+$")


@dataclass(frozen=True)
class EvalQuestion:
    question_id: str
    question_text: str
    question_type: str
    expected_chunk_ids: tuple[str, ...]
    expected_doc_ids: tuple[str, ...]
    expected_tax_year: str | None
    query_tax_year: str | None
    should_abstain: bool

    @property
    def has_gold_evidence(self) -> bool:
        return bool(self.expected_chunk_ids)

    @property
    def is_evidence_evaluated(self) -> bool:
        return bool(self.expected_chunk_ids) and not self.should_abstain

    @property
    def temporal_constraint_source(self) -> str:
        if self.query_tax_year:
            return "query"
        if self.expected_tax_year:
            return "gold_only"
        return "none"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run retrieval evaluation for BTaxBench Pilot14.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH), help="Annotated Pilot14 dataset JSONL.")
    parser.add_argument("--index-dir", default=str(DEFAULT_SPARSE_INDEX_DIR), help="Sparse index directory.")
    parser.add_argument("--dense-index-dir", default=str(DEFAULT_DENSE_INDEX_DIR), help="Dense index directory.")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON), help="Evaluation JSON output path.")
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD), help="Evaluation Markdown output path.")
    parser.add_argument("--top-k", type=int, default=5, help="Final number of hits to evaluate.")
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=list(DEFAULT_MODES),
        default=list(DEFAULT_MODES),
        help="Retrieval modes to run.",
    )
    return parser


def load_eval_questions(dataset_path: str | Path) -> list[EvalQuestion]:
    questions: list[EvalQuestion] = []
    with Path(dataset_path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            row = json.loads(stripped_line)
            question_id = row.get("question_id")
            question_text = row.get("question_text")
            if not question_id or not question_text:
                raise ValueError(f"Line {line_number}: question_id and question_text are required.")
            expected_chunk_ids = tuple(row.get("expected_chunk_ids") or ())
            expected_doc_ids = tuple(row.get("expected_doc_ids") or derive_expected_doc_ids(expected_chunk_ids))
            query_tax_year = preprocess_query(question_text).tax_year
            questions.append(
                EvalQuestion(
                    question_id=question_id,
                    question_text=question_text,
                    question_type=row.get("question_type", "unknown"),
                    expected_chunk_ids=expected_chunk_ids,
                    expected_doc_ids=expected_doc_ids,
                    expected_tax_year=row.get("expected_tax_year"),
                    query_tax_year=query_tax_year,
                    should_abstain=bool(row.get("should_abstain", False)),
                )
            )
    return questions


def derive_expected_doc_ids(expected_chunk_ids: tuple[str, ...]) -> list[str]:
    doc_ids: list[str] = []
    seen_doc_ids: set[str] = set()
    for chunk_id in expected_chunk_ids:
        match = CHUNK_ID_PAGE_PATTERN.match(chunk_id)
        doc_id = match.group("doc_id") if match else chunk_id.split("-p", 1)[0]
        if doc_id and doc_id not in seen_doc_ids:
            doc_ids.append(doc_id)
            seen_doc_ids.add(doc_id)
    return doc_ids


def expected_doc_page_pairs(expected_chunk_ids: tuple[str, ...]) -> set[tuple[str, int]]:
    pairs: set[tuple[str, int]] = set()
    for chunk_id in expected_chunk_ids:
        match = CHUNK_ID_PAGE_PATTERN.match(chunk_id)
        if not match:
            continue
        pairs.add((match.group("doc_id"), int(match.group("page"))))
    return pairs


def first_gold_rank(hits: list[RetrievalHit], expected_chunk_ids: tuple[str, ...]) -> int | None:
    expected = set(expected_chunk_ids)
    if not expected:
        return None
    for rank, hit in enumerate(hits, start=1):
        if hit.chunk_id in expected:
            return rank
    return None


def hit_at_rank(rank: int | None, k: int, *, has_gold_evidence: bool) -> bool | None:
    if not has_gold_evidence:
        return None
    return bool(rank and rank <= k)


def doc_hit_at_k(hits: list[RetrievalHit], expected_doc_ids: tuple[str, ...], k: int) -> bool | None:
    if not expected_doc_ids:
        return None
    expected = set(expected_doc_ids)
    return any(hit.doc_id in expected for hit in hits[:k])


def page_hit_at_k(hits: list[RetrievalHit], expected_chunk_ids: tuple[str, ...], k: int) -> bool | None:
    expected_pairs = expected_doc_page_pairs(expected_chunk_ids)
    if not expected_pairs:
        return None
    return any((hit.doc_id, hit.page_no) in expected_pairs for hit in hits[:k])


def adjacent_page_hit_at_k(hits: list[RetrievalHit], expected_chunk_ids: tuple[str, ...], k: int) -> bool | None:
    expected_pairs = expected_doc_page_pairs(expected_chunk_ids)
    if not expected_pairs:
        return None
    for hit in hits[:k]:
        for expected_doc_id, expected_page in expected_pairs:
            if hit.doc_id == expected_doc_id and abs(hit.page_no - expected_page) <= 1:
                return True
    return False


def top_hit_tax_year_status(
    hits: list[RetrievalHit],
    expected_tax_year: str | None,
    query_tax_year: str | None,
) -> dict[str, bool | None | str]:
    top_hit = hits[0] if hits else None
    top_hit_tax_year = top_hit.tax_year if top_hit else None
    query_year_correct = None if not query_tax_year else bool(top_hit_tax_year == query_tax_year)
    wrong_query_year = None if not query_tax_year else bool(top_hit_tax_year and top_hit_tax_year != query_tax_year)
    if not expected_tax_year:
        return {
            "top_hit_tax_year": top_hit_tax_year,
            "tax_year_correct": None,
            "wrong_year": None,
            "missing_top_hit_tax_year": None,
            "query_tax_year_correct": query_year_correct,
            "wrong_query_tax_year": wrong_query_year,
        }
    return {
        "top_hit_tax_year": top_hit_tax_year,
        "tax_year_correct": bool(top_hit_tax_year == expected_tax_year),
        "wrong_year": bool(top_hit_tax_year and top_hit_tax_year != expected_tax_year),
        "missing_top_hit_tax_year": bool(top_hit and not top_hit_tax_year),
        "query_tax_year_correct": query_year_correct,
        "wrong_query_tax_year": wrong_query_year,
    }


def evaluate_question_hits(question: EvalQuestion, mode: str, hits: list[RetrievalHit]) -> dict[str, Any]:
    gold_rank = first_gold_rank(hits, question.expected_chunk_ids)
    tax_year_status = top_hit_tax_year_status(hits, question.expected_tax_year, question.query_tax_year)
    return {
        "question_id": question.question_id,
        "question_type": question.question_type,
        "question_text": question.question_text,
        "mode": mode,
        "should_abstain": question.should_abstain,
        "evaluated_for_evidence_metrics": question.is_evidence_evaluated,
        "expected_chunk_ids": list(question.expected_chunk_ids),
        "expected_doc_ids": list(question.expected_doc_ids),
        "expected_tax_year": question.expected_tax_year,
        "query_tax_year": question.query_tax_year,
        "temporal_constraint_source": question.temporal_constraint_source,
        "gold_rank": gold_rank,
        "gold_chunk_in_top_1": hit_at_rank(gold_rank, 1, has_gold_evidence=question.has_gold_evidence),
        "gold_chunk_in_top_3": hit_at_rank(gold_rank, 3, has_gold_evidence=question.has_gold_evidence),
        "gold_chunk_in_top_5": hit_at_rank(gold_rank, 5, has_gold_evidence=question.has_gold_evidence),
        "doc_hit_at_5": doc_hit_at_k(hits, question.expected_doc_ids, 5),
        "page_hit_at_5": page_hit_at_k(hits, question.expected_chunk_ids, 5),
        "adjacent_page_hit_at_5": adjacent_page_hit_at_k(hits, question.expected_chunk_ids, 5),
        **tax_year_status,
        "top_hits": [
            {
                "rank": rank,
                "chunk_id": hit.chunk_id,
                "doc_id": hit.doc_id,
                "page_no": hit.page_no,
                "section_id": hit.section_id,
                "chunk_type": hit.chunk_type,
                "tax_year": hit.tax_year,
                "score": hit.score,
                "text_preview": hit.original_text[:220].replace("\n", " "),
            }
            for rank, hit in enumerate(hits, start=1)
        ],
    }


def compute_mode_metrics(row_results: list[dict[str, Any]]) -> dict[str, Any]:
    answerable_rows = [row for row in row_results if row["evaluated_for_evidence_metrics"]]
    tax_year_rows = [row for row in answerable_rows if row["expected_tax_year"]]
    explicit_tax_year_rows = [row for row in answerable_rows if row["query_tax_year"]]
    gold_only_tax_year_rows = [
        row for row in answerable_rows if row["expected_tax_year"] and not row["query_tax_year"]
    ]
    abstention_rows = [row for row in row_results if row["should_abstain"]]
    evidence_count = len(answerable_rows)
    tax_year_count = len(tax_year_rows)
    explicit_tax_year_count = len(explicit_tax_year_rows)
    gold_only_tax_year_count = len(gold_only_tax_year_rows)

    def ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    hit_counts = {
        f"evidence_hit_at_{k}": sum(1 for row in answerable_rows if row[f"gold_chunk_in_top_{k}"])
        for k in TOP_K_VALUES
    }
    reciprocal_rank_sum = sum((1.0 / row["gold_rank"]) for row in answerable_rows if row["gold_rank"])
    tax_year_correct_count = sum(1 for row in tax_year_rows if row["tax_year_correct"])
    wrong_year_count = sum(1 for row in tax_year_rows if row["wrong_year"])
    missing_tax_year_count = sum(1 for row in tax_year_rows if row["missing_top_hit_tax_year"])
    explicit_tax_year_correct_count = sum(1 for row in explicit_tax_year_rows if row["query_tax_year_correct"])
    explicit_wrong_year_count = sum(1 for row in explicit_tax_year_rows if row["wrong_query_tax_year"])
    gold_only_wrong_year_count = sum(1 for row in gold_only_tax_year_rows if row["wrong_year"])

    return {
        "total_questions": len(row_results),
        "answerable_evidence_questions": evidence_count,
        "abstention_questions": len(abstention_rows),
        "counts": {
            **hit_counts,
            "tax_year_correct_top1": tax_year_correct_count,
            "wrong_year_top1": wrong_year_count,
            "explicit_tax_year_correct_top1": explicit_tax_year_correct_count,
            "explicit_wrong_year_top1": explicit_wrong_year_count,
            "gold_only_wrong_year_top1": gold_only_wrong_year_count,
            "missing_top_hit_tax_year": missing_tax_year_count,
            "doc_hit_at_5": sum(1 for row in answerable_rows if row["doc_hit_at_5"]),
            "page_hit_at_5": sum(1 for row in answerable_rows if row["page_hit_at_5"]),
            "adjacent_page_hit_at_5": sum(1 for row in answerable_rows if row["adjacent_page_hit_at_5"]),
        },
        "metrics": {
            "evidence_hit_at_1": ratio(hit_counts["evidence_hit_at_1"], evidence_count),
            "evidence_hit_at_3": ratio(hit_counts["evidence_hit_at_3"], evidence_count),
            "evidence_hit_at_5": ratio(hit_counts["evidence_hit_at_5"], evidence_count),
            "mrr": round(reciprocal_rank_sum / evidence_count, 4) if evidence_count else 0.0,
            "tax_year_accuracy_top1": ratio(tax_year_correct_count, tax_year_count),
            "wrong_year_retrieval_rate_top1": ratio(wrong_year_count, tax_year_count),
            "explicit_tax_year_accuracy_top1": ratio(explicit_tax_year_correct_count, explicit_tax_year_count),
            "explicit_wrong_year_retrieval_rate_top1": ratio(explicit_wrong_year_count, explicit_tax_year_count),
            "gold_only_wrong_year_retrieval_rate_top1": ratio(gold_only_wrong_year_count, gold_only_tax_year_count),
            "missing_top_hit_tax_year_rate": ratio(missing_tax_year_count, tax_year_count),
            "doc_hit_at_5": ratio(sum(1 for row in answerable_rows if row["doc_hit_at_5"]), evidence_count),
            "page_hit_at_5": ratio(sum(1 for row in answerable_rows if row["page_hit_at_5"]), evidence_count),
            "adjacent_page_hit_at_5": ratio(
                sum(1 for row in answerable_rows if row["adjacent_page_hit_at_5"]),
                evidence_count,
            ),
        },
        "temporal_question_counts": {
            "expected_tax_year_questions": tax_year_count,
            "explicit_query_tax_year_questions": explicit_tax_year_count,
            "gold_only_tax_year_questions": gold_only_tax_year_count,
        },
    }


def run_mode_for_question(
    *,
    mode: str,
    question: EvalQuestion,
    top_k: int,
    sparse_index: Any,
    index_dir: str | Path,
    dense_index_dir: str | Path,
) -> list[RetrievalHit]:
    if mode == "sparse":
        return search_sparse_index(query=question.question_text, index=sparse_index, top_k=top_k).hits
    if mode == "dense":
        return [
            RetrievalHit(**hit)
            for hit in dense_search(
                question.question_text,
                top_k=top_k,
                index_dir=dense_index_dir,
            )
        ]
    if mode == "hybrid":
        response = run_hybrid_retrieval(
            query=question.question_text,
            sparse_top_k=max(top_k * 2, 10),
            dense_top_k=max(top_k * 2, 10),
            final_top_k=top_k,
            index_dir=index_dir,
            dense_index_dir=dense_index_dir,
        )
        return response.final_hits
    raise ValueError(f"Unsupported retrieval mode: {mode}")


def run_retrieval_eval(
    *,
    dataset_path: str | Path,
    index_dir: str | Path,
    dense_index_dir: str | Path,
    modes: list[str],
    top_k: int,
) -> dict[str, Any]:
    questions = load_eval_questions(dataset_path)
    sparse_index = load_sparse_index(index_dir)
    dense_metadata = load_dense_index_metadata(dense_index_dir)
    row_results: list[dict[str, Any]] = []
    logger = get_logger(__name__)

    for index, question in enumerate(questions, start=1):
        logger.info(
            "Running retrieval eval question",
            extra={"question_id": question.question_id, "position": index, "total": len(questions)},
        )
        for mode in modes:
            hits = run_mode_for_question(
                mode=mode,
                question=question,
                top_k=top_k,
                sparse_index=sparse_index,
                index_dir=index_dir,
                dense_index_dir=dense_index_dir,
            )
            row_results.append(evaluate_question_hits(question, mode, hits))

    mode_summaries = {
        mode: compute_mode_metrics([row for row in row_results if row["mode"] == mode])
        for mode in modes
    }
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_path": str(dataset_path),
        "index_dir": str(index_dir),
        "dense_index_dir": str(dense_index_dir),
        "dense_index_metadata": dense_metadata,
        "top_k": top_k,
        "modes": modes,
        "mode_summaries": mode_summaries,
        "rows": row_results,
    }


def write_json_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def format_bool(value: Any) -> str:
    if value is None:
        return "n/a"
    return "yes" if value else "no"


def write_markdown_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Pilot14 Automated Retrieval Evaluation",
        "",
        f"Date: {report['created_at']}",
        "",
        f"Dataset: `{report['dataset_path']}`",
        "",
        f"Sparse index: `{report['index_dir']}`",
        "",
        f"Dense index: `{report['dense_index_dir']}`",
        "",
        f"Dense index type: `{report['dense_index_metadata'].get('index_type', 'unknown')}`",
        "",
    ]
    if report["dense_index_metadata"].get("index_type") == "dense_overlap_placeholder":
        lines.extend(
            [
                "Warning: dense mode is still an overlap placeholder, not a real embedding baseline.",
                "",
            ]
        )

    lines.extend(
        [
            "## Summary",
            "",
            "| mode | questions | answerable | abstain | Hit@1 | Hit@3 | Hit@5 | MRR | Tax-Year Acc@1 | Wrong-Year Rate@1 | Explicit Year Acc@1 | Explicit Wrong-Year@1 | Gold-Only Wrong-Year@1 | Missing-Year Rate@1 | Doc Hit@5 | Page Hit@5 | Adjacent Page Hit@5 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for mode, summary in report["mode_summaries"].items():
        metrics = summary["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    mode,
                    str(summary["total_questions"]),
                    str(summary["answerable_evidence_questions"]),
                    str(summary["abstention_questions"]),
                    f"{metrics['evidence_hit_at_1']:.4f}",
                    f"{metrics['evidence_hit_at_3']:.4f}",
                    f"{metrics['evidence_hit_at_5']:.4f}",
                    f"{metrics['mrr']:.4f}",
                    f"{metrics['tax_year_accuracy_top1']:.4f}",
                    f"{metrics['wrong_year_retrieval_rate_top1']:.4f}",
                    f"{metrics['explicit_tax_year_accuracy_top1']:.4f}",
                    f"{metrics['explicit_wrong_year_retrieval_rate_top1']:.4f}",
                    f"{metrics['gold_only_wrong_year_retrieval_rate_top1']:.4f}",
                    f"{metrics['missing_top_hit_tax_year_rate']:.4f}",
                    f"{metrics['doc_hit_at_5']:.4f}",
                    f"{metrics['page_hit_at_5']:.4f}",
                    f"{metrics['adjacent_page_hit_at_5']:.4f}",
                ]
            )
            + " |"
        )

    misses = [
        row
        for row in report["rows"]
        if row["evaluated_for_evidence_metrics"] and not row["gold_chunk_in_top_5"]
    ]
    wrong_year_rows = [
        row
        for row in report["rows"]
        if row["evaluated_for_evidence_metrics"] and row["wrong_year"]
    ]
    explicit_wrong_year_rows = [
        row
        for row in wrong_year_rows
        if row["temporal_constraint_source"] == "query"
    ]
    gold_only_wrong_year_rows = [
        row
        for row in wrong_year_rows
        if row["temporal_constraint_source"] == "gold_only"
    ]
    lines.extend(["", "## Top Misses", ""])
    if not misses:
        lines.append("No strict Hit@5 misses.")
    else:
        lines.extend(
            [
                "| question_id | mode | expected | top-5 | note |",
                "|---|---|---|---|---|",
            ]
        )
        for row in misses[:30]:
            expected = ", ".join(f"`{chunk_id}`" for chunk_id in row["expected_chunk_ids"]) or "-"
            top_ids = ", ".join(f"`{hit['chunk_id']}`" for hit in row["top_hits"][:5]) or "-"
            note = "same doc nearby" if row["adjacent_page_hit_at_5"] else "strict miss"
            lines.append(f"| `{row['question_id']}` | {row['mode']} | {expected} | {top_ids} | {note} |")

    lines.extend(["", "## Wrong-Year Rows", ""])
    if not wrong_year_rows:
        lines.append("No wrong-year top hits among answerable questions.")
    else:
        lines.append(
            f"Explicit query-year failures: {len(explicit_wrong_year_rows)}. "
            f"Gold-only temporal failures: {len(gold_only_wrong_year_rows)}."
        )
        lines.append("")
        lines.extend(
            [
                "| question_id | mode | source | query_tax_year | expected_tax_year | top_hit_tax_year | top_hit |",
                "|---|---|---|---:|---:|---:|---|",
            ]
        )
        for row in wrong_year_rows:
            top_hit = row["top_hits"][0]["chunk_id"] if row["top_hits"] else "-"
            lines.append(
                f"| `{row['question_id']}` | {row['mode']} | {row['temporal_constraint_source']} | {row['query_tax_year']} | {row['expected_tax_year']} | {row['top_hit_tax_year']} | `{top_hit}` |"
            )

    lines.extend(
        [
            "",
            "## Per-Question Rows",
            "",
            "| question_id | type | mode | abstain | temporal_source | query_year | expected_year | rank | Hit@1 | Hit@3 | Hit@5 | doc@5 | page@5 | adjacent@5 | tax_year_ok | wrong_year | top-3 |",
            "|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        top_3 = ", ".join(f"`{hit['chunk_id']}`" for hit in row["top_hits"][:3]) or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['question_id']}`",
                    row["question_type"],
                    row["mode"],
                    format_bool(row["should_abstain"]),
                    row["temporal_constraint_source"],
                    str(row["query_tax_year"] or "n/a"),
                    str(row["expected_tax_year"] or "n/a"),
                    str(row["gold_rank"] or "n/a"),
                    format_bool(row["gold_chunk_in_top_1"]),
                    format_bool(row["gold_chunk_in_top_3"]),
                    format_bool(row["gold_chunk_in_top_5"]),
                    format_bool(row["doc_hit_at_5"]),
                    format_bool(row["page_hit_at_5"]),
                    format_bool(row["adjacent_page_hit_at_5"]),
                    format_bool(row["tax_year_correct"]),
                    format_bool(row["wrong_year"]),
                    top_3,
                ]
            )
            + " |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    configure_logging()
    args = build_argument_parser().parse_args()
    report = run_retrieval_eval(
        dataset_path=args.dataset,
        index_dir=args.index_dir,
        dense_index_dir=args.dense_index_dir,
        modes=args.modes,
        top_k=args.top_k,
    )
    json_path = write_json_report(report, args.output_json)
    markdown_path = write_markdown_report(report, args.output_md)
    print(f"Retrieval evaluation written to {json_path} and {markdown_path}")
    print(json.dumps(report["mode_summaries"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
