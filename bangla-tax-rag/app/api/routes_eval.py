from fastapi import APIRouter

from app.core.schemas import EvalRequest, EvalResponse
from app.eval.metrics import evaluate_predictions

router = APIRouter(tags=["evaluation"])


@router.post("/evaluate", response_model=EvalResponse)
async def evaluate_system(request: EvalRequest) -> EvalResponse:
    scores = evaluate_predictions(request.predictions, request.references)
    return EvalResponse(
        status="completed",
        metric_name=scores["metric_name"],
        score=scores["score"],
        details=scores["details"],
    )
