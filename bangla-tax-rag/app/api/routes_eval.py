import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.schemas import EvalRequest, EvalResponse
from app.core.settings import get_settings
from app.core.utils import ensure_directory, ensure_file_exists
from app.eval.metrics import evaluate_dataset_file

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


@router.post("/evaluate", response_model=EvalResponse)
async def evaluate_system(request: EvalRequest) -> EvalResponse:
    try:
        return _run_evaluation(request)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "missing_file", "message": str(exc)},
        ) from exc
