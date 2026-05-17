from __future__ import annotations

import argparse
import base64
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryItemRecord  # noqa: E402
from app.inventory.image_feedback import list_image_search_corrections  # noqa: E402
from app.inventory.image_matcher import (  # noqa: E402
    ImageMatchResult,
    ImageMatcher,
    apply_owner_corrections,
    finalize_image_search,
    primary_image_url,
    query_image_id_from_b64,
)


DEFAULT_EVAL_PATH = ROOT / "evaluation" / "q1_image_search_research_set.jsonl"
DEFAULT_CATALOG_PATH = ROOT / "data" / "inventory" / "catalog.jsonl"
DEFAULT_OUT_DIR = ROOT / "results"


METHOD_DESCRIPTIONS = {
    "full_system": (
        "Current production-style path: visual retrieval when available, "
        "owner corrections, reference guard, variant/design resolver, and answer policy."
    ),
    "metadata_baseline": (
        "Deterministic metadata fallback: text/category/color cues plus the same decision policy."
    ),
    "no_identity_ablation": (
        "Same retrieval candidates as the full path, but variant_group_id/design_id removed before the decision layer."
    ),
    "policy_oracle": (
        "Decision-policy ceiling test: injects the known image product as a high-score raw visual hit."
    ),
    "naive_oracle_top1": (
        "Unsafe baseline: high-score top-1 is called exact without reference-image or business-rule gating."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a Q1-style image-search research pass with metrics, ablations, and reports."
    )
    parser.add_argument("--eval-path", default=str(DEFAULT_EVAL_PATH))
    parser.add_argument("--catalog-path", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--engine",
        choices=("metadata", "clip", "auto"),
        default="metadata",
        help="Retrieval engine for full_system. Use metadata for fast local paper-pipeline checks.",
    )
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument(
        "--methods",
        nargs="*",
        default=[
            "full_system",
            "metadata_baseline",
            "no_identity_ablation",
            "policy_oracle",
            "naive_oracle_top1",
        ],
        choices=tuple(METHOD_DESCRIPTIONS),
    )
    args = parser.parse_args()

    catalog_path = Path(args.catalog_path)
    eval_path = Path(args.eval_path)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog = load_catalog(catalog_path)
    cases = load_jsonl(eval_path)
    if not cases:
        raise SystemExit(f"No cases found in {eval_path}")

    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    all_rows: list[dict[str, Any]] = []
    method_warnings: dict[str, list[str]] = defaultdict(list)

    for case in cases:
        query_image_b64 = image_to_b64(ROOT / case["image_path"])
        raw_results, full_engine, full_warning = retrieve_candidates(
            catalog=catalog,
            case=case,
            image_b64=query_image_b64,
            engine=args.engine,
            top_k=max(args.top_k * 4, 12),
        )
        if full_warning:
            method_warnings["full_system"].append(full_warning)

        for method in args.methods:
            started = perf_counter()
            if method == "full_system":
                response = decision_response(
                    run_decision(
                        catalog=catalog,
                        raw_results=raw_results,
                        case=case,
                        image_b64=query_image_b64,
                        top_k=args.top_k,
                    ),
                    method=method,
                    retrieval_engine=full_engine,
                    latency_ms=(perf_counter() - started) * 1000,
                )
            elif method == "metadata_baseline":
                metadata_raw, metadata_engine, _ = retrieve_candidates(
                    catalog=catalog,
                    case=case,
                    image_b64=query_image_b64,
                    engine="metadata",
                    top_k=max(args.top_k * 4, 12),
                )
                response = decision_response(
                    run_decision(
                        catalog=catalog,
                        raw_results=metadata_raw,
                        case=case,
                        image_b64=query_image_b64,
                        top_k=args.top_k,
                    ),
                    method=method,
                    retrieval_engine=metadata_engine,
                    latency_ms=(perf_counter() - started) * 1000,
                )
            elif method == "no_identity_ablation":
                stripped_catalog = clone_catalog(catalog, strip_identity=True)
                response = decision_response(
                    run_decision(
                        catalog=stripped_catalog,
                        raw_results=raw_results,
                        case=case,
                        image_b64=query_image_b64,
                        top_k=args.top_k,
                    ),
                    method=method,
                    retrieval_engine=full_engine,
                    latency_ms=(perf_counter() - started) * 1000,
                )
            elif method == "policy_oracle":
                oracle_raw = oracle_candidate(catalog, case)
                response = decision_response(
                    run_decision(
                        catalog=catalog,
                        raw_results=oracle_raw,
                        case=case,
                        image_b64=query_image_b64,
                        top_k=args.top_k,
                    ),
                    method=method,
                    retrieval_engine="oracle_raw_hit",
                    latency_ms=(perf_counter() - started) * 1000,
                )
            elif method == "naive_oracle_top1":
                response = naive_top1_response(
                    catalog=catalog,
                    raw_results=oracle_candidate(catalog, case),
                    method=method,
                    latency_ms=(perf_counter() - started) * 1000,
                )
            else:  # pragma: no cover - argparse choices guard this
                raise ValueError(method)

            issues = check_case(case, response)
            all_rows.append(
                {
                    "case_id": case["case_id"],
                    "task_type": case.get("task_type", "unknown"),
                    "language": case.get("language", "unknown"),
                    "difficulty": case.get("difficulty", "unknown"),
                    "method": method,
                    "issues": issues,
                    "passed": not issues,
                    "response": response,
                    "case": case,
                }
            )

    metrics = compute_metrics(all_rows)
    payload = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "eval_path": str(eval_path.relative_to(ROOT) if eval_path.is_relative_to(ROOT) else eval_path),
        "catalog_path": str(catalog_path.relative_to(ROOT) if catalog_path.is_relative_to(ROOT) else catalog_path),
        "engine": args.engine,
        "methods": args.methods,
        "method_descriptions": METHOD_DESCRIPTIONS,
        "warnings": {key: sorted(set(values)) for key, values in method_warnings.items()},
        "metrics": metrics,
        "rows": all_rows,
    }

    json_path = out_dir / f"q1_image_research_pass_{run_id}.json"
    md_path = out_dir / f"q1_image_research_pass_{run_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    full = metrics["by_method"].get("full_system", {})
    print(f"Q1 image research pass written:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print(
        "  full_system: "
        f"{full.get('strict_pass_rate', 0):.1%} strict pass, "
        f"{full.get('label_accuracy', 0):.1%} label accuracy, "
        f"{full.get('target_top3_recall', 0):.1%} target top-3 recall"
    )
    return 0


def load_catalog(path: Path) -> dict[str, InventoryItemRecord]:
    catalog: dict[str, InventoryItemRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = InventoryItemRecord.model_validate(json.loads(line))
        catalog[item.product_id] = item
    return catalog


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def image_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def retrieve_candidates(
    *,
    catalog: dict[str, InventoryItemRecord],
    case: dict[str, Any],
    image_b64: str,
    engine: str,
    top_k: int,
) -> tuple[list[ImageMatchResult], str, str | None]:
    query_text = case.get("query_text") or ""
    if engine in {"clip", "auto"}:
        try:
            from app.inventory.clip_matcher import CLIPImageMatcher, precompute_catalog_embeddings

            clip_available = CLIPImageMatcher.is_available()
            if clip_available:
                precompute_catalog_embeddings(catalog)
                return (
                    CLIPImageMatcher().search(
                        query_text=query_text,
                        image_b64=image_b64,
                        catalog=catalog,
                        category_hint=case.get("category_hint"),
                        color_hint=case.get("color_hint"),
                        budget_max=case.get("budget_max"),
                        top_k=top_k,
                    ),
                    "clip",
                    None,
                )
            if engine == "clip":
                warning = "CLIP requested but unavailable; metadata fallback used."
            else:
                warning = "CLIP unavailable in auto mode; metadata fallback used."
        except Exception as exc:
            warning = f"CLIP retrieval failed; metadata fallback used: {exc}"
    else:
        warning = None

    return (
        ImageMatcher(catalog).search(
            query_text=query_text,
            image_b64=image_b64,
            category_hint=case.get("category_hint"),
            color_hint=case.get("color_hint"),
            budget_max=case.get("budget_max"),
            top_k=top_k,
        ),
        "metadata",
        warning,
    )


def run_decision(
    *,
    catalog: dict[str, InventoryItemRecord],
    raw_results: list[ImageMatchResult],
    case: dict[str, Any],
    image_b64: str,
    top_k: int,
):
    query_image_id = query_image_id_from_b64(image_b64)
    corrected = apply_owner_corrections(
        catalog=catalog,
        results=raw_results,
        query_image_id=query_image_id,
        corrections=list_image_search_corrections(limit=1000),
    )
    return finalize_image_search(
        catalog=catalog,
        results=corrected,
        query_text=case.get("query_text") or "",
        requested_color=case.get("color_hint"),
        top_k=top_k,
    )


def oracle_candidate(
    catalog: dict[str, InventoryItemRecord],
    case: dict[str, Any],
) -> list[ImageMatchResult]:
    product_id = Path(case["image_path"]).parent.name
    item = catalog.get(product_id)
    if item is None:
        return []
    return [
        ImageMatchResult(
            product_id=item.product_id,
            name=item.name,
            score=0.99,
            match_type="visual_similar",
            reasons=("oracle image-path anchor",),
            price=item.price,
            currency=item.currency,
            stock=item.stock,
            image_url=primary_image_url(item),
        )
    ]


def clone_catalog(
    catalog: dict[str, InventoryItemRecord],
    *,
    strip_identity: bool = False,
    trust_references: bool = False,
) -> dict[str, InventoryItemRecord]:
    cloned: dict[str, InventoryItemRecord] = {}
    for product_id, item in catalog.items():
        attrs = dict(item.attributes or {})
        if strip_identity:
            for key in ("variant_group_id", "variant_group_name", "design_id"):
                attrs.pop(key, None)
        images = list(item.images or [])
        if trust_references:
            images = [
                image.model_copy(update={"kind": "product_photo", "is_reference": False})
                for image in images
            ]
        cloned[product_id] = item.model_copy(update={"attributes": attrs, "images": images}, deep=True)
    return cloned


def decision_response(
    decision,
    *,
    method: str,
    retrieval_engine: str,
    latency_ms: float,
) -> dict[str, Any]:
    return {
        "method": method,
        "retrieval_engine": retrieval_engine,
        "latency_ms": latency_ms,
        "answer": decision.answer,
        "decision_label": decision.decision_label,
        "primary_product_id": decision.primary_product_id,
        "same_design_variant_ids": list(decision.same_design_variant_ids),
        "similar_product_ids": list(decision.similar_product_ids),
        "requested_color": decision.requested_color,
        "requested_size": decision.requested_size,
        "available_colors": list(decision.available_colors),
        "score_breakdown": decision.score_breakdown,
        "hits": [hit_to_dict(hit) for hit in decision.hits],
        "follow_up_question": decision.follow_up_question,
    }


def naive_top1_response(
    *,
    catalog: dict[str, InventoryItemRecord],
    raw_results: list[ImageMatchResult],
    method: str,
    latency_ms: float,
) -> dict[str, Any]:
    if not raw_results:
        return {
            "method": method,
            "retrieval_engine": "oracle_raw_hit",
            "latency_ms": latency_ms,
            "answer": "No match.",
            "decision_label": "no_confident_match",
            "primary_product_id": None,
            "same_design_variant_ids": [],
            "similar_product_ids": [],
            "available_colors": [],
            "score_breakdown": {"policy": "naive_top1"},
            "hits": [],
        }
    top = raw_results[0]
    item = catalog[top.product_id]
    label = "confirmed_exact" if top.score >= 0.9 else "similar_style"
    hit = hit_to_dict(
        ImageMatchResult(
            product_id=top.product_id,
            name=item.name,
            score=top.score,
            match_type=top.match_type,
            reasons=top.reasons + ("naive top-1 exact threshold",),
            price=item.price,
            currency=item.currency,
            stock=item.stock,
            image_url=primary_image_url(item),
            decision_label=label,
            score_breakdown={"visual_score": top.score, "policy": "naive_top1"},
        )
    )
    return {
        "method": method,
        "retrieval_engine": "oracle_raw_hit",
        "latency_ms": latency_ms,
        "answer": f"Naive top-1 says exact match: {item.name}.",
        "decision_label": label,
        "primary_product_id": top.product_id,
        "same_design_variant_ids": [],
        "similar_product_ids": [],
        "available_colors": [],
        "score_breakdown": {"visual_score": top.score, "policy": "naive_top1"},
        "hits": [hit],
    }


def hit_to_dict(hit: ImageMatchResult) -> dict[str, Any]:
    data = asdict(hit)
    data["reasons"] = list(hit.reasons)
    return data


def check_case(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    hit_ids = [hit.get("product_id") for hit in response.get("hits", [])]
    primary = response.get("primary_product_id")

    expected_label = case.get("expected_decision_label")
    if expected_label and response.get("decision_label") != expected_label:
        issues.append(f"expected decision_label={expected_label}, got {response.get('decision_label')}")

    forbidden_label = case.get("forbidden_decision_label")
    if forbidden_label and response.get("decision_label") == forbidden_label:
        issues.append(f"forbidden decision_label={forbidden_label}")

    expected_primary = case.get("expected_primary_product_id")
    if expected_primary and expected_primary not in {primary, *hit_ids[:3]}:
        issues.append(f"expected {expected_primary} in primary/top-3, got {primary} / {hit_ids[:3]}")

    expected_targets = set(case.get("expected_target_product_ids") or [])
    if expected_targets and not (expected_targets & {primary, *hit_ids[:3]}):
        issues.append(f"none of expected target ids appeared in primary/top-3: {sorted(expected_targets)}")

    forbidden_ids = set(case.get("forbidden_product_ids") or [])
    if forbidden_ids:
        if primary in forbidden_ids:
            issues.append(f"forbidden product {primary} appeared as primary")
        bad_hits = [hid for hid in hit_ids if hid in forbidden_ids]
        if bad_hits:
            issues.append(f"forbidden product(s) {bad_hits} appeared in hits")

    expected_variants = set(case.get("expected_same_design_variant_ids") or [])
    if expected_variants:
        actual_variants = set(response.get("same_design_variant_ids") or []) | set(hit_ids)
        missing = expected_variants - actual_variants
        if missing:
            issues.append(f"missing expected variants: {sorted(missing)}")

    expected_colors = set(case.get("expected_available_colors") or [])
    if expected_colors:
        actual_colors = set(response.get("available_colors") or [])
        missing = expected_colors - actual_colors
        if missing:
            issues.append(f"missing expected colors: {sorted(missing)}")

    expected_absent_color = case.get("expected_absent_color")
    if expected_absent_color and expected_absent_color in set(response.get("available_colors") or []):
        issues.append(f"color should be absent but appeared in available_colors: {expected_absent_color}")

    expected_requested_color = case.get("expected_requested_color")
    if expected_requested_color and response.get("requested_color") != expected_requested_color:
        issues.append(f"expected requested_color={expected_requested_color}, got {response.get('requested_color')}")

    expected_requested_size = case.get("expected_requested_size")
    if expected_requested_size and response.get("requested_size") != expected_requested_size:
        issues.append(f"expected requested_size={expected_requested_size}, got {response.get('requested_size')}")

    expected_category = case.get("expected_category")
    if expected_category:
        expected_category_cf = expected_category.casefold()
        categories = {
            str((hit.get("score_breakdown") or {}).get("category", "")).casefold()
            for hit in response.get("hits", [])
        }
        names = " ".join(str(hit.get("name", "")) for hit in response.get("hits", [])).casefold()
        if expected_category_cf not in categories and expected_category_cf not in names:
            issues.append(f"expected category signal {expected_category} in hits")

    expected_answer = case.get("expected_answer_contains")
    if expected_answer:
        answer = str(response.get("answer", "") or response.get("final_answer", ""))
        if expected_answer.casefold() not in answer.casefold():
            issues.append(f"expected answer to contain {expected_answer!r}")

    expected_answer_not = case.get("expected_answer_not_contains")
    if expected_answer_not:
        answer = str(response.get("answer", "") or response.get("final_answer", ""))
        if expected_answer_not.casefold() in answer.casefold():
            issues.append(f"answer should not contain {expected_answer_not!r}")

    return issues


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_method: dict[str, Any] = {}
    for method in sorted({row["method"] for row in rows}):
        method_rows = [row for row in rows if row["method"] == method]
        by_method[method] = method_metrics(method_rows)

    full_rows = [row for row in rows if row["method"] == "full_system"]
    by_task: dict[str, Any] = {}
    for task in sorted({row["task_type"] for row in full_rows}):
        by_task[task] = method_metrics([row for row in full_rows if row["task_type"] == task])

    return {"by_method": by_method, "full_system_by_task": by_task}


def method_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    label_expected = [
        row for row in rows
        if row["case"].get("expected_decision_label")
    ]
    primary_expected = [
        row for row in rows
        if row["case"].get("expected_primary_product_id")
    ]
    target_expected = [
        row for row in rows
        if row["case"].get("expected_target_product_ids")
    ]
    variant_expected = [
        row for row in rows
        if row["case"].get("expected_same_design_variant_ids")
    ]
    color_expected = [
        row for row in rows
        if row["case"].get("expected_available_colors")
    ]
    forbidden_rows = [
        row for row in rows
        if row["case"].get("forbidden_product_ids") or row["case"].get("forbidden_decision_label")
    ]
    reference_rows = [
        row for row in rows
        if "reference_guard" in set(row["case"].get("metric_tags") or [])
    ]

    return {
        "cases": len(rows),
        "strict_pass_rate": ratio(sum(1 for row in rows if row["passed"]), len(rows)),
        "label_accuracy": ratio(
            sum(
                1 for row in label_expected
                if row["response"].get("decision_label") == row["case"].get("expected_decision_label")
            ),
            len(label_expected),
        ),
        "primary_or_top3_accuracy": ratio(
            sum(1 for row in primary_expected if expected_primary_in_top3(row)),
            len(primary_expected),
        ),
        "target_top3_recall": mean([target_top3_recall(row) for row in target_expected]),
        "same_design_variant_recall": mean([same_design_recall(row) for row in variant_expected]),
        "available_color_recall": mean([available_color_recall(row) for row in color_expected]),
        "forbidden_violation_rate": ratio(
            sum(1 for row in forbidden_rows if has_forbidden_violation(row)),
            len(forbidden_rows),
            default=0.0,
        ),
        "false_exact_on_reference_rate": ratio(
            sum(1 for row in reference_rows if row["response"].get("decision_label") == "confirmed_exact"),
            len(reference_rows),
            default=0.0,
        ),
        "avg_latency_ms": mean([float(row["response"].get("latency_ms") or 0.0) for row in rows]),
    }


def expected_primary_in_top3(row: dict[str, Any]) -> bool:
    expected = row["case"].get("expected_primary_product_id")
    if not expected:
        return True
    response = row["response"]
    hit_ids = [hit.get("product_id") for hit in response.get("hits", [])]
    return expected in {response.get("primary_product_id"), *hit_ids[:3]}


def target_top3_recall(row: dict[str, Any]) -> float:
    expected = set(row["case"].get("expected_target_product_ids") or [])
    if not expected:
        return 1.0
    response = row["response"]
    hit_ids = [hit.get("product_id") for hit in response.get("hits", [])]
    actual = {response.get("primary_product_id"), *hit_ids[:3]}
    return len(expected & actual) / len(expected)


def same_design_recall(row: dict[str, Any]) -> float:
    expected = set(row["case"].get("expected_same_design_variant_ids") or [])
    if not expected:
        return 1.0
    response = row["response"]
    hit_ids = {hit.get("product_id") for hit in response.get("hits", [])}
    actual = set(response.get("same_design_variant_ids") or []) | hit_ids
    return len(expected & actual) / len(expected)


def available_color_recall(row: dict[str, Any]) -> float:
    expected = set(row["case"].get("expected_available_colors") or [])
    if not expected:
        return 1.0
    actual = set(row["response"].get("available_colors") or [])
    return len(expected & actual) / len(expected)


def has_forbidden_violation(row: dict[str, Any]) -> bool:
    case = row["case"]
    response = row["response"]
    if case.get("forbidden_decision_label") and response.get("decision_label") == case["forbidden_decision_label"]:
        return True
    forbidden = set(case.get("forbidden_product_ids") or [])
    if not forbidden:
        return False
    hit_ids = {hit.get("product_id") for hit in response.get("hits", [])}
    return response.get("primary_product_id") in forbidden or bool(forbidden & hit_ids)


def ratio(numerator: int, denominator: int, *, default: float = 1.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def mean(values: list[float]) -> float:
    if not values:
        return 1.0
    return statistics.fmean(values)


def render_markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines: list[str] = []
    lines.append("# Q1 Image Search Research Pass")
    lines.append("")
    lines.append(f"- Run ID: `{payload['run_id']}`")
    lines.append(f"- Created: `{payload['created_at']}`")
    lines.append(f"- Dataset: `{payload['eval_path']}`")
    lines.append(f"- Catalog: `{payload['catalog_path']}`")
    lines.append(f"- Retrieval engine requested for full system: `{payload['engine']}`")
    lines.append("")
    lines.append("## Research Question")
    lines.append("")
    lines.append(
        "Can a boutique inventory chatbot combine visual retrieval, catalog identity, "
        "reference-image safety, and structured business facts to answer customer screenshot queries reliably?"
    )
    lines.append("")
    lines.append("## Methods")
    lines.append("")
    for method in payload["methods"]:
        lines.append(f"- `{method}`: {payload['method_descriptions'][method]}")
    lines.append("")
    warnings = payload.get("warnings") or {}
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for method, items in warnings.items():
            for item in items:
                lines.append(f"- `{method}`: {item}")
        lines.append("")

    lines.append("## Summary Metrics")
    lines.append("")
    lines.append(
        "| Method | Cases | Strict Pass | Label Acc | Primary/Top-3 | Target Top-3 | Same-Design Recall | Color Recall | Forbidden Viol. | Ref False Exact | Avg Latency |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for method, row in metrics["by_method"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{method}`",
                    str(row.get("cases", 0)),
                    pct(row.get("strict_pass_rate", 0)),
                    pct(row.get("label_accuracy", 0)),
                    pct(row.get("primary_or_top3_accuracy", 0)),
                    pct(row.get("target_top3_recall", 0)),
                    pct(row.get("same_design_variant_recall", 0)),
                    pct(row.get("available_color_recall", 0)),
                    pct(row.get("forbidden_violation_rate", 0)),
                    pct(row.get("false_exact_on_reference_rate", 0)),
                    f"{row.get('avg_latency_ms', 0):.1f} ms",
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Full-System Breakdown By Task")
    lines.append("")
    lines.append("| Task | Cases | Strict Pass | Label Acc | Target Top-3 | Forbidden Viol. | Avg Latency |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for task, row in metrics["full_system_by_task"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{task}`",
                    str(row.get("cases", 0)),
                    pct(row.get("strict_pass_rate", 0)),
                    pct(row.get("label_accuracy", 0)),
                    pct(row.get("target_top3_recall", 0)),
                    pct(row.get("forbidden_violation_rate", 0)),
                    f"{row.get('avg_latency_ms', 0):.1f} ms",
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Failure Notes")
    lines.append("")
    failures = [row for row in payload["rows"] if not row["passed"]]
    if not failures:
        lines.append("No strict-check failures in this pass.")
    else:
        lines.append("| Method | Case | Task | Decision | Primary | Issues |")
        lines.append("|---|---|---|---|---|---|")
        for row in failures[:80]:
            response = row["response"]
            issue_text = "<br>".join(escape_pipe(issue) for issue in row["issues"])
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{row['method']}`",
                        f"`{row['case_id']}`",
                        f"`{row['task_type']}`",
                        f"`{response.get('decision_label')}`",
                        f"`{response.get('primary_product_id')}`",
                        issue_text,
                    ]
                )
                + " |"
            )
        if len(failures) > 80:
            lines.append(f"\nOnly first 80 failures shown. Total failures: {len(failures)}.")

    lines.append("")
    lines.append("## Q1 Readiness Assessment")
    lines.append("")
    lines.append(
        "This is a first-pass research pipeline, not yet a Q1-grade empirical result. "
        "It creates the machinery a Q1 paper needs: task-labeled cases, baselines, ablations, safety metrics, "
        "and reproducible artifacts. The current catalog still mixes shop-owned product photos with reference/demo images, "
        "so production claims must stay conservative."
    )
    lines.append("")
    lines.append("Strongest publishable direction:")
    lines.append("")
    lines.append(
        "- Evaluate how catalog identity fields (`variant_group_id`, `design_id`, stock/size facts) reduce false exact matches "
        "and improve same-design retrieval over raw visual similarity."
    )
    lines.append(
        "- Add a real shop-owned image dataset and compare against CLIP-only, metadata-only, and no-identity ablations."
    )
    lines.append(
        "- Report false-exact rate, same-design recall, top-3 retrieval, and answer-grounding violations rather than only retrieval accuracy."
    )
    lines.append("")
    lines.append("## One-Pass Reproduction Command")
    lines.append("")
    lines.append("```bash")
    method_args = " ".join(payload["methods"])
    lines.append(
        f".venv/bin/python scripts/run_q1_image_research_pass.py --engine {payload['engine']} --methods {method_args}"
    )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def escape_pipe(value: str) -> str:
    return value.replace("|", "\\|")


if __name__ == "__main__":
    raise SystemExit(main())
