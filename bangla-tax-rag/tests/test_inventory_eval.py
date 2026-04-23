from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.eval.inventory_matrix import run_inventory_eval_matrix
from app.main import app


def test_inventory_eval_matrix_passes_phase8_cases() -> None:
    summary = run_inventory_eval_matrix()

    assert summary["suite_name"] == "inventory_phase8_eval_matrix"
    assert summary["total_cases"] == 7
    assert summary["passed_cases"] == 7
    assert summary["failed_cases"] == 0
    assert summary["accuracy"] == 1.0
    assert summary["retrieval_stage_failures"] == 0
    assert summary["answer_stage_failures"] == 0
    assert summary["abstain_metrics"]["false_positive_abstains"] == 0
    assert summary["abstain_metrics"]["false_negative_abstains"] == 0
    assert summary["family_breakdown"]["recommendation"]["total_cases"] >= 4
    assert summary["covered_failure_modes"]["false_spec_claim"] == 1
    assert summary["covered_failure_modes"]["false_in_stock_claim"] == 1


@pytest.mark.anyio
async def test_inventory_eval_endpoint_runs_subset_and_writes_outputs(tmp_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/evaluate/inventory",
            json={
                "case_ids": ["exact-product-detail", "budget-ceiling-violation"],
                "output_dir": str(tmp_path),
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
    for output_path in payload["output_paths"]:
        assert Path(output_path).exists()
