import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.schemas import EvalRequest, EvalResponse, InventoryEvalRequest
from app.core.settings import get_settings
from app.core.utils import ensure_directory, ensure_file_exists
from app.eval.metrics import evaluate_dataset_file
from app.eval.inventory_matrix import run_inventory_eval_matrix

router = APIRouter(tags=["evaluation"])


def _run_evaluation(request: EvalRequest) -> EvalResponse:
    settings = get_settings()
    dataset_path = ensure_file_exists(request.dataset_path)
    output_dir = ensure_directory(request.output_dir or settings.results_dir)
    dataset_metrics = evaluate_dataset_file(dataset_path)
    metrics_summary = {
        "dataset_path": str(dataset_path),
        "retrieval_modes": request.retrieval_modes,
        "generate_answers": request.generate_answers,
        "dataset_metrics": dataset_metrics,
    }
    output_paths = [str(output_dir / "evaluation_summary.json")]
    Path(output_paths[0]).write_text(
        json.dumps(metrics_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return EvalResponse(status="completed", output_paths=output_paths, metrics_summary=metrics_summary)


def _run_inventory_evaluation(request: InventoryEvalRequest) -> EvalResponse:
    settings = get_settings()
    output_dir = ensure_directory(request.output_dir or settings.results_dir)
    summary_path = output_dir / "inventory_eval_summary.json"
    baseline_summary, baseline_source = _resolve_inventory_baseline(
        request=request,
        default_summary_path=summary_path,
    )
    metrics_summary = run_inventory_eval_matrix(case_ids=request.case_ids or None)
    regression_diff = _build_inventory_regression_diff(
        current_summary=metrics_summary,
        baseline_summary=baseline_summary,
        baseline_source=baseline_source,
    )
    metrics_summary["regression_diff"] = regression_diff
    case_results_path = output_dir / "inventory_eval_case_results.jsonl"
    regression_diff_path = output_dir / "inventory_eval_regression_diff.json"
    summary_path.write_text(
        json.dumps(metrics_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    case_results_lines = [
        json.dumps(case_result, ensure_ascii=False)
        for case_result in metrics_summary.get("case_results", [])
    ]
    case_results_path.write_text(
        "\n".join(case_results_lines) + ("\n" if case_results_lines else ""),
        encoding="utf-8",
    )
    regression_diff_path.write_text(
        json.dumps(regression_diff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return EvalResponse(
        status="completed",
        output_paths=[str(summary_path), str(case_results_path), str(regression_diff_path)],
        metrics_summary=metrics_summary,
    )


def _resolve_inventory_baseline(
    *,
    request: InventoryEvalRequest,
    default_summary_path: Path,
) -> tuple[dict[str, object] | None, str | None]:
    if request.baseline_summary_path:
        baseline_path = ensure_file_exists(request.baseline_summary_path)
        return _load_summary_json(baseline_path), str(baseline_path)
    if default_summary_path.exists():
        return _load_summary_json(default_summary_path), str(default_summary_path)
    return None, None


def _load_summary_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in summary file: {path}")
    return payload


def _build_inventory_regression_diff(
    *,
    current_summary: dict[str, object],
    baseline_summary: dict[str, object] | None,
    baseline_source: str | None,
) -> dict[str, object]:
    if baseline_summary is None:
        return {
            "status": "no_baseline",
            "baseline_source": None,
            "improved_case_ids": [],
            "regressed_case_ids": [],
            "unchanged_failing_case_ids": [],
            "new_case_ids": [],
            "removed_case_ids": [],
        }

    current_cases = _case_results_by_id(current_summary)
    baseline_cases = _case_results_by_id(baseline_summary)
    shared_case_ids = sorted(set(current_cases).intersection(baseline_cases))
    improved_case_ids = sorted(
        case_id for case_id in shared_case_ids if not baseline_cases[case_id]["passed"] and current_cases[case_id]["passed"]
    )
    regressed_case_ids = sorted(
        case_id for case_id in shared_case_ids if baseline_cases[case_id]["passed"] and not current_cases[case_id]["passed"]
    )
    unchanged_failing_case_ids = sorted(
        case_id for case_id in shared_case_ids if not baseline_cases[case_id]["passed"] and not current_cases[case_id]["passed"]
    )
    new_case_ids = sorted(set(current_cases).difference(baseline_cases))
    removed_case_ids = sorted(set(baseline_cases).difference(current_cases))

    current_accuracy = _safe_float(current_summary.get("accuracy"))
    baseline_accuracy = _safe_float(baseline_summary.get("accuracy"))
    family_accuracy_deltas = _metric_map_delta(
        current_map=_extract_family_accuracies(current_summary),
        baseline_map=_extract_family_accuracies(baseline_summary),
    )
    answer_engine_rate_deltas = _metric_map_delta(
        current_map=_safe_metric_map(current_summary.get("answer_engine_rates")),
        baseline_map=_safe_metric_map(baseline_summary.get("answer_engine_rates")),
    )
    abstain_metric_deltas = _int_metric_delta_map(
        current_map=_safe_int_metric_map(current_summary.get("abstain_metrics")),
        baseline_map=_safe_int_metric_map(baseline_summary.get("abstain_metrics")),
    )

    return {
        "status": "compared",
        "baseline_source": baseline_source,
        "baseline_total_cases": _safe_int(baseline_summary.get("total_cases")),
        "current_total_cases": _safe_int(current_summary.get("total_cases")),
        "accuracy": {
            "baseline": baseline_accuracy,
            "current": current_accuracy,
            "delta": round(current_accuracy - baseline_accuracy, 3),
        },
        "retrieval_stage_failures_delta": _safe_int(current_summary.get("retrieval_stage_failures"))
        - _safe_int(baseline_summary.get("retrieval_stage_failures")),
        "answer_stage_failures_delta": _safe_int(current_summary.get("answer_stage_failures"))
        - _safe_int(baseline_summary.get("answer_stage_failures")),
        "family_accuracy_deltas": family_accuracy_deltas,
        "answer_engine_rate_deltas": answer_engine_rate_deltas,
        "abstain_metric_deltas": abstain_metric_deltas,
        "improved_case_ids": improved_case_ids,
        "regressed_case_ids": regressed_case_ids,
        "unchanged_failing_case_ids": unchanged_failing_case_ids,
        "new_case_ids": new_case_ids,
        "removed_case_ids": removed_case_ids,
        "summary": (
            f"{len(improved_case_ids)} improved, {len(regressed_case_ids)} regressed, "
            f"{len(unchanged_failing_case_ids)} still failing."
        ),
    }


def _case_results_by_id(summary: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_cases = summary.get("case_results")
    if not isinstance(raw_cases, list):
        return {}
    mapped: dict[str, dict[str, object]] = {}
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        if isinstance(case_id, str) and case_id:
            mapped[case_id] = item
    return mapped


def _extract_family_accuracies(summary: dict[str, object]) -> dict[str, float]:
    family_breakdown = summary.get("family_breakdown")
    if not isinstance(family_breakdown, dict):
        return {}
    metrics: dict[str, float] = {}
    for family, payload in family_breakdown.items():
        if not isinstance(family, str) or not isinstance(payload, dict):
            continue
        metrics[family] = _safe_float(payload.get("accuracy"))
    return metrics


def _metric_map_delta(
    *,
    current_map: dict[str, float],
    baseline_map: dict[str, float],
) -> dict[str, dict[str, float]]:
    deltas: dict[str, dict[str, float]] = {}
    for key in sorted(set(current_map).union(baseline_map)):
        baseline = baseline_map.get(key, 0.0)
        current = current_map.get(key, 0.0)
        deltas[key] = {
            "baseline": baseline,
            "current": current,
            "delta": round(current - baseline, 3),
        }
    return deltas


def _int_metric_delta_map(
    *,
    current_map: dict[str, int],
    baseline_map: dict[str, int],
) -> dict[str, dict[str, int]]:
    deltas: dict[str, dict[str, int]] = {}
    for key in sorted(set(current_map).union(baseline_map)):
        baseline = baseline_map.get(key, 0)
        current = current_map.get(key, 0)
        deltas[key] = {
            "baseline": baseline,
            "current": current,
            "delta": current - baseline,
        }
    return deltas


def _safe_metric_map(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {
        key: _safe_float(metric_value)
        for key, metric_value in value.items()
        if isinstance(key, str)
    }


def _safe_int_metric_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: _safe_int(metric_value)
        for key, metric_value in value.items()
        if isinstance(key, str)
    }


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@router.post("/evaluate", response_model=EvalResponse)
async def evaluate_system(request: EvalRequest) -> EvalResponse:
    try:
        return _run_evaluation(request)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_file", "message": str(exc)},
        ) from exc


@router.post("/evaluate/inventory", response_model=EvalResponse)
async def evaluate_inventory_system(request: InventoryEvalRequest) -> EvalResponse:
    try:
        return _run_inventory_evaluation(request)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_inventory_eval_baseline", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_inventory_eval_request", "message": str(exc)},
        ) from exc
