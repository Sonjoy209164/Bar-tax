from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/feedback", tags=["feedback"])

_FEEDBACK_PATH = Path("data/feedback/feedback.jsonl")


class FeedbackRequest(BaseModel):
    session_id: str
    question: str
    answer: str
    rating: str          # "up" | "down"
    comment: str | None = None
    intent: str | None = None
    product_ids: list[str] = []


class FeedbackResponse(BaseModel):
    status: str
    feedback_id: str
    message: str


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
        "created_at": now,
    }
    with _FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return FeedbackResponse(
        status="saved",
        feedback_id=fid,
        message="Thank you for your feedback!" if request.rating == "up" else "Sorry about that — we'll improve.",
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
