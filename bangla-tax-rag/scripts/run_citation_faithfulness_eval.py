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

from app.core.utils import extract_informative_query_terms, normalize_text, split_sentences
from app.retrieval.sparse import load_chunk_records_from_jsonl


DEFAULT_DATASET_PATH = Path("data/btaxbench/pilot14/btaxbench_pilot14_v0_1.jsonl")
DEFAULT_CHUNKS_PATH = Path("data/processed/btax14/chunks.jsonl")
DEFAULT_OUTPUT_JSON = Path("results/pilot14/citation_faithfulness_v0_1.json")
DEFAULT_OUTPUT_MD = Path("results/pilot14/citation_faithfulness_v0_1.md")
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*%?")
ABSTENTION_PATTERN = re.compile(
    r"(নির্ভরযোগ্য\s+উত্তর|নিশ্চিত\s+উত্তর|উত্তর\s+দেওয়া\s+যাবে\s+না|উত্তর\s+দেয়া\s+যাবে\s+না|"
    r"প্রমাণে\s+নেই|প্রমাণ\s+নেই|বলা\s+নেই|সরাসরি\s+নেই|নেই;\s*তাই|নির্ধারণ\s+করা\s+যায়\s+না|"
    r"নির্ধারণ\s+করা\s+যায়\s+না|উদ্ধৃত\s+প্রমাণ\s+ছাড়া|উদ্ধৃত\s+প্রমাণ\s+ছাড়া|"
    r"নির্ভরযোগ্যভাবে\s+বলা\s+যাবে\s+না|অনুমান\s+করা\s+যাবে\s+না|abstain|outside|not\s+evidenced|cannot\s+answer)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClaimSupport:
    claim_text: str
    supported: bool | None
    reason: str
    informative_overlap: int
    informative_ratio: float
    missing_numbers: tuple[str, ...]


def canonical_number(value: str) -> str:
    return value.replace(",", "").replace(".", "").strip().rstrip("%")


def extract_numbers(text: str) -> set[str]:
    return {canonical_number(match) for match in NUMBER_PATTERN.findall(normalize_text(text)) if canonical_number(match)}


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped_line = line.strip()
            if stripped_line:
                rows.append(json.loads(stripped_line))
    return rows


def load_evidence_text_by_chunk_id(chunks_path: str | Path) -> dict[str, str]:
    chunks = load_chunk_records_from_jsonl(chunks_path)
    return {
        chunk.chunk_id: normalize_text(
            "\n".join(
                part
                for part in [
                    chunk.doc_title,
                    " ".join(chunk.heading_path),
                    chunk.original_text,
                    chunk.normalized_text,
                ]
                if part
            )
        )
        for chunk in chunks
    }


def split_answer_claims(answer_text: str | None) -> list[str]:
    if not answer_text:
        return []
    claims: list[str] = []
    for sentence in split_sentences(answer_text):
        for fragment in re.split(r";|;|\n", sentence):
            cleaned = fragment.strip(" \t।.")
            if cleaned:
                claims.append(cleaned)
    return claims


def evaluate_claim_support(
    claim_text: str,
    evidence_text: str,
    *,
    question_type: str | None = None,
) -> ClaimSupport:
    normalized_claim = normalize_text(claim_text)
    normalized_evidence = normalize_text(evidence_text)
    claim_numbers = extract_numbers(normalized_claim)
    evidence_numbers = extract_numbers(normalized_evidence)
    missing_numbers = tuple(sorted(number for number in claim_numbers if number not in evidence_numbers))

    informative_terms = extract_informative_query_terms(normalized_claim, question_type)
    if len(informative_terms) <= 1 and not claim_numbers:
        return ClaimSupport(
            claim_text=claim_text,
            supported=None,
            reason="too_short_for_heuristic_support",
            informative_overlap=0,
            informative_ratio=0.0,
            missing_numbers=missing_numbers,
        )

    evidence_terms = extract_informative_query_terms(normalized_evidence, question_type)
    informative_overlap = len(informative_terms & evidence_terms)
    informative_ratio = informative_overlap / max(len(informative_terms), 1)

    if missing_numbers:
        return ClaimSupport(
            claim_text=claim_text,
            supported=False,
            reason="claim_number_not_found_in_cited_evidence",
            informative_overlap=informative_overlap,
            informative_ratio=round(informative_ratio, 4),
            missing_numbers=missing_numbers,
        )

    if informative_ratio >= 0.35 or informative_overlap >= 4:
        return ClaimSupport(
            claim_text=claim_text,
            supported=True,
            reason="lexical_evidence_overlap",
            informative_overlap=informative_overlap,
            informative_ratio=round(informative_ratio, 4),
            missing_numbers=missing_numbers,
        )

    if claim_numbers and informative_overlap >= 2:
        return ClaimSupport(
            claim_text=claim_text,
            supported=True,
            reason="numeric_claim_with_minimal_context_overlap",
            informative_overlap=informative_overlap,
            informative_ratio=round(informative_ratio, 4),
            missing_numbers=missing_numbers,
        )

    return ClaimSupport(
        claim_text=claim_text,
        supported=False,
        reason="low_overlap_with_cited_evidence",
        informative_overlap=informative_overlap,
        informative_ratio=round(informative_ratio, 4),
        missing_numbers=missing_numbers,
    )


def evaluate_dataset_citation_faithfulness(
    *,
    dataset_path: str | Path,
    chunks_path: str | Path,
) -> dict[str, Any]:
    dataset_rows = load_jsonl(dataset_path)
    evidence_by_chunk_id = load_evidence_text_by_chunk_id(chunks_path)
    row_results: list[dict[str, Any]] = []

    evaluated_claims = 0
    supported_claims = 0
    unsupported_claims = 0
    skipped_short_claims = 0
    answerable_rows = 0
    fully_supported_rows = 0
    abstention_rows = 0
    correct_abstentions = 0

    for row in dataset_rows:
        question_id = row.get("question_id", "")
        should_abstain = bool(row.get("should_abstain", False))
        answer_text = row.get("answer_text") or ""
        expected_chunk_ids = list(row.get("expected_chunk_ids") or [])

        if should_abstain:
            abstention_rows += 1
            abstention_ok = bool(ABSTENTION_PATTERN.search(normalize_text(answer_text)))
            correct_abstentions += int(abstention_ok)
            row_results.append(
                {
                    "question_id": question_id,
                    "should_abstain": should_abstain,
                    "abstention_supported": abstention_ok,
                    "expected_chunk_ids": expected_chunk_ids,
                    "claim_results": [],
                }
            )
            continue

        answerable_rows += 1
        evidence_text = "\n".join(evidence_by_chunk_id.get(chunk_id, "") for chunk_id in expected_chunk_ids)
        missing_evidence_ids = [chunk_id for chunk_id in expected_chunk_ids if chunk_id not in evidence_by_chunk_id]
        claim_results: list[dict[str, Any]] = []
        row_evaluated_claims = 0
        row_supported_claims = 0

        for claim in split_answer_claims(answer_text):
            claim_support = evaluate_claim_support(claim, evidence_text, question_type=row.get("question_type"))
            claim_result = {
                "claim_text": claim_support.claim_text,
                "supported": claim_support.supported,
                "reason": claim_support.reason,
                "informative_overlap": claim_support.informative_overlap,
                "informative_ratio": claim_support.informative_ratio,
                "missing_numbers": list(claim_support.missing_numbers),
            }
            claim_results.append(claim_result)
            if claim_support.supported is None:
                skipped_short_claims += 1
                continue
            evaluated_claims += 1
            row_evaluated_claims += 1
            if claim_support.supported:
                supported_claims += 1
                row_supported_claims += 1
            else:
                unsupported_claims += 1

        row_fully_supported = bool(row_evaluated_claims) and row_supported_claims == row_evaluated_claims and not missing_evidence_ids
        fully_supported_rows += int(row_fully_supported)
        row_results.append(
            {
                "question_id": question_id,
                "should_abstain": should_abstain,
                "expected_chunk_ids": expected_chunk_ids,
                "missing_evidence_ids": missing_evidence_ids,
                "evaluated_claim_count": row_evaluated_claims,
                "supported_claim_count": row_supported_claims,
                "fully_supported": row_fully_supported,
                "claim_results": claim_results,
            }
        )

    precision = supported_claims / evaluated_claims if evaluated_claims else 0.0
    recall = fully_supported_rows / answerable_rows if answerable_rows else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    abstention_accuracy = correct_abstentions / abstention_rows if abstention_rows else 0.0

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_path": str(dataset_path),
        "chunks_path": str(chunks_path),
        "metric_scope": "heuristic_gold-answer_vs_gold-cited-chunks",
        "counts": {
            "rows": len(dataset_rows),
            "answerable_rows": answerable_rows,
            "abstention_rows": abstention_rows,
            "evaluated_claims": evaluated_claims,
            "supported_claims": supported_claims,
            "unsupported_claims": unsupported_claims,
            "skipped_short_claims": skipped_short_claims,
            "fully_supported_answerable_rows": fully_supported_rows,
            "correct_abstentions": correct_abstentions,
        },
        "metrics": {
            "citation_support_precision": round(precision, 4),
            "citation_support_recall": round(recall, 4),
            "citation_support_f1": round(f1, 4),
            "unsupported_claim_rate": round(unsupported_claims / evaluated_claims, 4) if evaluated_claims else 0.0,
            "abstention_accuracy": round(abstention_accuracy, 4),
        },
        "limitations": [
            "Heuristic lexical/numeric support check; not a replacement for expert legal annotation.",
            "Short polarity claims such as 'না' are skipped unless they contain enough content terms or numbers.",
            "This evaluates frozen gold answers against frozen gold evidence chunks, not generated answers yet.",
        ],
        "rows": row_results,
    }


def write_json_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_markdown_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = report["metrics"]
    counts = report["counts"]
    unsupported_rows = [
        row
        for row in report["rows"]
        if not row.get("should_abstain")
        and any(claim.get("supported") is False for claim in row.get("claim_results", []))
    ]

    lines = [
        "# Pilot14 v0.1 Citation Faithfulness Evaluation",
        "",
        f"Date: {report['created_at']}",
        "",
        f"Dataset: `{report['dataset_path']}`",
        "",
        f"Evidence chunks: `{report['chunks_path']}`",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| answerable rows | {counts['answerable_rows']} |",
        f"| abstention rows | {counts['abstention_rows']} |",
        f"| evaluated claims | {counts['evaluated_claims']} |",
        f"| supported claims | {counts['supported_claims']} |",
        f"| unsupported claims | {counts['unsupported_claims']} |",
        f"| skipped short claims | {counts['skipped_short_claims']} |",
        f"| citation support precision | {metrics['citation_support_precision']:.4f} |",
        f"| citation support recall | {metrics['citation_support_recall']:.4f} |",
        f"| citation support F1 | {metrics['citation_support_f1']:.4f} |",
        f"| unsupported claim rate | {metrics['unsupported_claim_rate']:.4f} |",
        f"| abstention accuracy | {metrics['abstention_accuracy']:.4f} |",
        "",
        "## Important Limitation",
        "",
        "This is a heuristic scaffold. It is useful for catching numeric and lexical citation problems, but final paper claims need manual adjudication or a stronger NLI-style verifier.",
        "",
        "## Unsupported Claim Samples",
        "",
    ]
    if not unsupported_rows:
        lines.append("No unsupported claims found by the heuristic.")
    else:
        lines.extend(["| question_id | unsupported claim | reason | missing numbers |", "|---|---|---|---|"])
        for row in unsupported_rows[:30]:
            for claim in row.get("claim_results", []):
                if claim.get("supported") is False:
                    claim_text = str(claim["claim_text"]).replace("|", "\\|")
                    missing_numbers = ", ".join(claim.get("missing_numbers") or [])
                    lines.append(
                        f"| `{row['question_id']}` | {claim_text} | {claim['reason']} | {missing_numbers or '-'} |"
                    )
                    break

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run heuristic citation faithfulness evaluation for BTaxBench Pilot14.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH), help="Frozen annotated dataset JSONL.")
    parser.add_argument("--chunks", default=str(DEFAULT_CHUNKS_PATH), help="Chunk JSONL used as cited evidence.")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON), help="Evaluation JSON output path.")
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD), help="Evaluation Markdown output path.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    report = evaluate_dataset_citation_faithfulness(dataset_path=args.dataset, chunks_path=args.chunks)
    json_path = write_json_report(report, args.output_json)
    markdown_path = write_markdown_report(report, args.output_md)
    print(f"Citation faithfulness evaluation written to {json_path} and {markdown_path}")
    print(json.dumps({"counts": report["counts"], "metrics": report["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
