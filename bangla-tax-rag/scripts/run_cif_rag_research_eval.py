from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schemas import InventoryItemRecord  # noqa: E402
from app.inventory.cif_engine import CifRagEngine  # noqa: E402
from app.inventory.image_matcher import ImageMatchResult, finalize_image_search  # noqa: E402


DEFAULT_EVAL_PATH = ROOT / "evaluation" / "cif_counterfactual_commerce_set.jsonl"
DEFAULT_CATALOG_PATH = ROOT / "data" / "inventory" / "catalog.jsonl"
DEFAULT_OUT_DIR = ROOT / "results"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CIF-RAG architecture evaluation.")
    parser.add_argument("--eval-path", default=str(DEFAULT_EVAL_PATH))
    parser.add_argument("--catalog-path", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()

    catalog = load_catalog(Path(args.catalog_path))
    cases = load_jsonl(Path(args.eval_path))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = CifRagEngine(catalog)

    rows: list[dict[str, Any]] = []
    for case in cases:
        started = perf_counter()
        product_id = Path(case["image_path"]).parent.name
        decision = finalize_image_search(
            catalog=catalog,
            results=[oracle_hit(catalog, product_id)],
            query_text=case.get("query_text") or "",
            top_k=args.top_k,
        )
        cif = engine.analyze(
            query_text=case.get("query_text") or "",
            has_image=True,
            decision=decision,
        )
        trace = cif.to_trace()
        latency_ms = round((perf_counter() - started) * 1000, 3)
        response = {
            "decision_label": decision.decision_label,
            "primary_product_id": decision.primary_product_id,
            "cif_rag": trace,
            "latency_ms": latency_ms,
        }
        issues = check_case(case, response)
        rows.append(
            {
                "case_id": case["case_id"],
                "passed": not issues,
                "issues": issues,
                "case": case,
                "response": response,
            }
        )

    payload = {
        "run_id": datetime.now(UTC).strftime("%Y%m%d_%H%M%S"),
        "created_at": datetime.now(UTC).isoformat(),
        "eval_path": str(Path(args.eval_path)),
        "catalog_path": str(Path(args.catalog_path)),
        "metrics": metrics(rows),
        "rows": rows,
    }
    json_path = out_dir / f"cif_rag_research_pass_{payload['run_id']}.json"
    md_path = out_dir / f"cif_rag_research_pass_{payload['run_id']}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print("CIF-RAG research eval written:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print(f"  pass_rate: {payload['metrics']['pass_rate']:.1%}")
    return 0 if payload["metrics"]["pass_rate"] == 1.0 else 1


def load_catalog(path: Path) -> dict[str, InventoryItemRecord]:
    catalog: dict[str, InventoryItemRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = InventoryItemRecord.model_validate(json.loads(line))
            catalog[item.product_id] = item
    return catalog


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def oracle_hit(catalog: dict[str, InventoryItemRecord], product_id: str) -> ImageMatchResult:
    item = catalog[product_id]
    return ImageMatchResult(
        product_id=item.product_id,
        name=item.name,
        score=0.99,
        match_type="visual_similar",
        reasons=("oracle image anchor",),
        price=item.price,
        currency=item.currency,
        stock=item.stock,
    )


def check_case(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    cif = response["cif_rag"]
    plan = cif["plan"]
    claims = cif["claims"]
    risk = cif["risk_decision"]

    if case.get("expected_query_family") and plan.get("query_family") != case["expected_query_family"]:
        issues.append(f"expected query_family={case['expected_query_family']}, got {plan.get('query_family')}")

    if case.get("expected_decision_label") and response.get("decision_label") != case["expected_decision_label"]:
        issues.append(f"expected decision_label={case['expected_decision_label']}, got {response.get('decision_label')}")

    expected_ops = set(case.get("expected_operations") or [])
    actual_ops = {format_operation(op) for op in plan.get("operations", [])}
    missing_ops = expected_ops - actual_ops
    if missing_ops:
        issues.append(f"missing expected operations: {sorted(missing_ops)}")

    expected_claims = set(case.get("expected_claim_types") or [])
    actual_claims = {claim.get("claim_type") for claim in claims.get("claims", [])}
    missing_claims = expected_claims - actual_claims
    if missing_claims:
        issues.append(f"missing expected claim types: {sorted(missing_claims)}")

    forbidden_claims = set(case.get("forbidden_claim_types") or [])
    bad_claims = forbidden_claims & actual_claims
    if bad_claims:
        issues.append(f"forbidden claim types appeared: {sorted(bad_claims)}")

    if "expected_safe_to_answer" in case and risk.get("safe_to_answer") != case["expected_safe_to_answer"]:
        issues.append(f"expected safe_to_answer={case['expected_safe_to_answer']}, got {risk.get('safe_to_answer')}")

    unsupported = [
        claim.get("claim_type")
        for claim in claims.get("claims", [])
        if not claim.get("supported") and claim.get("risk_level") == "high"
    ]
    if unsupported and case.get("expected_safe_to_answer", True):
        issues.append(f"unsupported high-risk claims: {unsupported}")

    return issues


def format_operation(operation: dict[str, Any]) -> str:
    value = operation.get("value")
    if value is None:
        return f"{operation.get('op')}:{operation.get('target')}"
    return f"{operation.get('op')}:{operation.get('target')}={value}"


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    passed = sum(1 for row in rows if row["passed"])
    plan_passed = 0
    claim_passed = 0
    risk_passed = 0
    for row in rows:
        issue_text = "\n".join(row["issues"])
        if "query_family" not in issue_text and "operations" not in issue_text:
            plan_passed += 1
        if "claim" not in issue_text:
            claim_passed += 1
        if "safe_to_answer" not in issue_text and "unsupported high-risk" not in issue_text:
            risk_passed += 1
    return {
        "cases": total,
        "pass_rate": passed / total if total else 1.0,
        "planner_pass_rate": plan_passed / total if total else 1.0,
        "claim_contract_pass_rate": claim_passed / total if total else 1.0,
        "risk_policy_pass_rate": risk_passed / total if total else 1.0,
        "avg_latency_ms": sum(row["response"]["latency_ms"] for row in rows) / total if total else 0.0,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    lines = [
        "# CIF-RAG Research Evaluation Pass",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Created: `{payload['created_at']}`",
        f"- Dataset: `{payload['eval_path']}`",
        f"- Catalog: `{payload['catalog_path']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Cases | {m['cases']} |",
        f"| Overall pass rate | {m['pass_rate'] * 100:.1f}% |",
        f"| Planner pass rate | {m['planner_pass_rate'] * 100:.1f}% |",
        f"| Claim contract pass rate | {m['claim_contract_pass_rate'] * 100:.1f}% |",
        f"| Risk policy pass rate | {m['risk_policy_pass_rate'] * 100:.1f}% |",
        f"| Avg latency | {m['avg_latency_ms']:.2f} ms |",
        "",
        "## Case Results",
        "",
        "| Case | Decision | Query Family | Safe | Issues |",
        "|---|---|---|---:|---|",
    ]
    for row in payload["rows"]:
        response = row["response"]
        cif = response["cif_rag"]
        issues = "<br>".join(row["issues"]) if row["issues"] else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['case_id']}`",
                    f"`{response['decision_label']}`",
                    f"`{cif['plan']['query_family']}`",
                    str(cif["risk_decision"]["safe_to_answer"]),
                    issues,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This eval checks the architectural pieces of CIF-RAG: counterfactual planning, typed commerce claims, and risk-cost policy. It is complementary to visual retrieval evaluation.",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
