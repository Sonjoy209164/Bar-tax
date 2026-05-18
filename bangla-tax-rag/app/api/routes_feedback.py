from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.inventory.feedback_to_eval import create_pending_case_from_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])

_FEEDBACK_PATH = Path("data/feedback/feedback.jsonl")


class FeedbackRequest(BaseModel):
    session_id: str
    question: str
    answer: str
    rating: Literal["up", "down"]
    comment: str | None = None
    intent: str | None = None
    product_ids: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    confidence_score: float | None = None
    abstained: bool | None = None
    abstention_reason: str | None = None
    answer_plan: dict[str, Any] | None = None
    source: str | None = "chat_ui"

    @field_validator("session_id", "question", "answer")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("field must not be empty")
        return stripped

    @field_validator("comment", "intent", "trace_id", "abstention_reason", "source")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("product_ids")
    @classmethod
    def normalize_product_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for product_id in value:
            stripped = str(product_id).strip()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str
    message: str
    pending_case_created: bool = False


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    _FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    fid = f"FB-{now[:10].replace('-','')}-{abs(hash(request.session_id + now)) % 100000:05d}"
    entry = {
        "feedback_id": fid,
        "session_id": request.session_id,
        "question": request.question,
        "answer": request.answer[:500],
        "rating": request.rating,
        "comment": request.comment,
        "intent": request.intent,
        "product_ids": request.product_ids,
        "trace_id": request.trace_id,
        "confidence_score": request.confidence_score,
        "abstained": request.abstained,
        "abstention_reason": request.abstention_reason,
        "answer_plan": _compact_answer_plan(request.answer_plan),
        "source": request.source or "chat_ui",
        "created_at": now,
    }
    with _FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    pending_case_created = create_pending_case_from_feedback(entry)
    return FeedbackResponse(
        status="saved",
        feedback_id=fid,
        message="Thank you for your feedback!" if request.rating == "up" else "Sorry about that — we'll improve.",
        pending_case_created=pending_case_created,
    )


@router.get("/report")
async def feedback_report() -> dict:
    if not _FEEDBACK_PATH.exists():
        return {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "satisfaction_rate": None, "worst_questions": []}

    entries = []
    for line in _FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                pass

    total = len(entries)
    ups = sum(1 for e in entries if e.get("rating") == "up")
    downs = sum(1 for e in entries if e.get("rating") == "down")
    satisfaction = round(ups / total, 3) if total else None

    intent_downs: Counter = Counter()
    for e in entries:
        if e.get("rating") == "down" and e.get("intent"):
            intent_downs[e["intent"]] += 1

    worst_questions = [
        {"question": e.get("question", ""), "intent": e.get("intent"), "comment": e.get("comment")}
        for e in entries
        if e.get("rating") == "down"
    ][-20:]

    return {
        "total": total,
        "thumbs_up": ups,
        "thumbs_down": downs,
        "satisfaction_rate": satisfaction,
        "worst_intents": dict(intent_downs.most_common(5)),
        "worst_questions": worst_questions,
    }


@router.get("/recent")
async def recent_feedback(limit: int = 20) -> list:
    if not _FEEDBACK_PATH.exists():
        return []
    entries = []
    for line in _FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                pass
    return entries[-limit:]


def _compact_answer_plan(answer_plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not answer_plan:
        return None
    allowed_keys = {
        "intent",
        "detected_intent",
        "intent_confidence",
        "primary_product_id",
        "alternative_product_ids",
        "cross_sell_product_ids",
        "excluded_product_ids",
        "abstain",
        "abstention_reason",
        "next_best_question",
    }
    return {
        key: value
        for key, value in answer_plan.items()
        if key in allowed_keys
    }
