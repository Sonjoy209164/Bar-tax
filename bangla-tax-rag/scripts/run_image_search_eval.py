from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_PATH = ROOT / "evaluation" / "image_search_gold_set.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run image-search gold-set checks against the local API.")
    parser.add_argument("--api-base", default=os.getenv("INVENTORY_API_BASE", "http://127.0.0.1:4837"))
    parser.add_argument("--api-key", default=os.getenv("API_ACCESS_KEY", "5230ff9faefe885d22345444e006cab576acdae5ea75d499"))
    parser.add_argument("--eval-path", default=str(DEFAULT_EVAL_PATH))
    args = parser.parse_args()

    cases = [json.loads(line) for line in Path(args.eval_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    failures: list[str] = []
    for case in cases:
        response = run_case(case, api_base=args.api_base, api_key=args.api_key)
        issues = check_case(case, response)
        status = "PASS" if not issues else "FAIL"
        print(f"{status} {case['case_id']} -> {response.get('decision_label')} {response.get('primary_product_id')}")
        if issues:
            for issue in issues:
                print(f"  - {issue}")
            failures.extend(f"{case['case_id']}: {issue}" for issue in issues)

    print(f"\n{len(cases) - len({f.split(':', 1)[0] for f in failures})}/{len(cases)} cases passed")
    return 1 if failures else 0


def run_case(case: dict[str, Any], *, api_base: str, api_key: str) -> dict[str, Any]:
    image_path = ROOT / case["image_path"]
    payload = json.dumps(
        {
            "query_text": case.get("query_text", ""),
            "image_b64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
            "top_k": 6,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/inventory/image-search",
        data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def check_case(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected_label = case.get("expected_decision_label")
    if expected_label and response.get("decision_label") != expected_label:
        issues.append(f"expected decision_label={expected_label}, got {response.get('decision_label')}")

    forbidden_label = case.get("forbidden_decision_label")
    if forbidden_label and response.get("decision_label") == forbidden_label:
        issues.append(f"forbidden decision_label={forbidden_label}")

    expected_primary = case.get("expected_primary_product_id")
    hit_ids = [hit.get("product_id") for hit in response.get("hits", [])]
    if expected_primary and expected_primary not in {response.get("primary_product_id"), *hit_ids[:3]}:
        issues.append(f"expected {expected_primary} in primary/top-3, got {response.get('primary_product_id')} / {hit_ids[:3]}")

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

    expected_category = case.get("expected_category")
    if expected_category:
        categories = {
            str((hit.get("score_breakdown") or {}).get("category", "")).casefold()
            for hit in response.get("hits", [])
        }
        names = " ".join(str(hit.get("name", "")) for hit in response.get("hits", [])).casefold()
        if expected_category.casefold() not in categories and expected_category.casefold() not in names:
            issues.append(f"expected category signal {expected_category} in hits")

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
