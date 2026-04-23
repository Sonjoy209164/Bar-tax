from pathlib import Path
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.eval.inventory_matrix import run_inventory_eval_matrix
from app.main import app


def test_inventory_eval_matrix_passes_phase8_cases() -> None:
    summary = run_inventory_eval_matrix()

    assert summary["suite_name"] == "inventory_phase8_eval_matrix"
    assert summary["total_cases"] == 14
    assert summary["passed_cases"] == 14
    assert summary["failed_cases"] == 0
    assert summary["accuracy"] == 1.0
    assert summary["retrieval_stage_failures"] == 0
    assert summary["answer_stage_failures"] == 0
    assert summary["abstain_metrics"]["false_positive_abstains"] == 0
    assert summary["abstain_metrics"]["false_negative_abstains"] == 0
    assert summary["family_breakdown"]["recommendation"]["total_cases"] >= 4
    assert summary["family_breakdown"]["diagnosis_root_cause"]["total_cases"] == 1
    assert summary["family_breakdown"]["planning_agentic_workflow"]["total_cases"] == 1
    assert summary["covered_failure_modes"]["wrong_product_type"] == 1
    assert summary["covered_failure_modes"]["false_spec_claim"] == 1
    assert summary["covered_failure_modes"]["false_in_stock_claim"] == 1
    assert summary["covered_failure_modes"]["bad_comparison"] == 1
    assert summary["covered_failure_modes"]["bad_cross_sell"] == 1
    assert summary["covered_failure_modes"]["hallucinated_business_rationale"] == 3
    wrong_type_case = next(case for case in summary["case_results"] if case["case_id"] == "wrong-product-type")
    assert wrong_type_case["response"]["primary_product_id"] == "prod-headphone"
    assert "KeyForge Mechanical Keyboard" not in wrong_type_case["response"]["answer"]
    compare_case = next(case for case in summary["case_results"] if case["case_id"] == "agentic-compare")
    assert compare_case["response"]["execution_path"] == "inventory_agentic"
    assert compare_case["trace"]["retrieval_step_actions"][-1] == "align_comparison_facts"
    diagnosis_case = next(case for case in summary["case_results"] if case["case_id"] == "agentic-diagnosis-root-cause")
    assert diagnosis_case["response"]["execution_path"] == "inventory_agentic"
    assert diagnosis_case["trace"]["retrieval_step_actions"][-1] == "diagnose_root_cause_facts"
    assert "Returns read:" in diagnosis_case["response"]["answer"]
    planning_case = next(case for case in summary["case_results"] if case["case_id"] == "agentic-operational-planning")
    assert planning_case["response"]["execution_path"] == "inventory_agentic"
    assert planning_case["trace"]["retrieval_step_actions"][-1] == "compose_operational_plan"
    assert "Supplier-risk read:" in planning_case["response"]["answer"]
    missing_domain_case = next(case for case in summary["case_results"] if case["case_id"] == "agentic-missing-domain-abstain")
    assert missing_domain_case["response"]["execution_path"] == "inventory_agentic_missing_domain_abstain"
    assert missing_domain_case["response"]["abstained"] is True


@pytest.mark.anyio
async def test_inventory_eval_endpoint_runs_subset_and_writes_outputs(tmp_path: Path) -> None:
    baseline_path = tmp_path / "inventory_eval_baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "total_cases": 2,
                "accuracy": 0.5,
                "retrieval_stage_failures": 1,
                "answer_stage_failures": 0,
                "family_breakdown": {
                    "product_detail": {"accuracy": 0.0},
                    "recommendation": {"accuracy": 1.0},
                },
                "answer_engine_rates": {"deterministic": 1.0},
                "abstain_metrics": {
                    "expected_abstain_cases": 1,
                    "expected_non_abstain_cases": 1,
                    "false_positive_abstains": 1,
                    "false_negative_abstains": 0,
                },
                "case_results": [
                    {"case_id": "exact-product-detail", "passed": False},
                    {"case_id": "budget-ceiling-violation", "passed": True},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/evaluate/inventory",
            json={
                "case_ids": ["exact-product-detail", "budget-ceiling-violation"],
                "output_dir": str(tmp_path),
                "baseline_summary_path": str(baseline_path),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["metrics_summary"]["selected_case_ids"] == [
        "exact-product-detail",
        "budget-ceiling-violation",
    ]
    assert payload["metrics_summary"]["passed_cases"] == 2
    regression_diff = payload["metrics_summary"]["regression_diff"]
    assert regression_diff["status"] == "compared"
    assert regression_diff["improved_case_ids"] == ["exact-product-detail"]
    assert regression_diff["regressed_case_ids"] == []
    assert regression_diff["accuracy"]["delta"] == 0.5
    for output_path in payload["output_paths"]:
        assert Path(output_path).exists()
