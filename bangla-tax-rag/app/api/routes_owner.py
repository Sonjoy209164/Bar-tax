"""
Shop owner dashboard endpoints.

The owner uses these to see how the bot is performing and what needs
attention. All endpoints are read-only except `/owner/cases/approve` and
`/owner/escalations/{id}/resolve`.

Mounted under prefix `/owner`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.inventory.conversion_tracker import summarize_conversions
from app.inventory.escalation import (
    list_pending_escalations,
    mark_escalation_resolved,
)
from app.inventory.feedback_to_eval import (
    approve_case,
    harvest_bad_feedback_to_pending,
    list_approved_cases,
    list_pending_cases,
)

router = APIRouter(prefix="/owner", tags=["owner"])


# ── Conversion funnel ────────────────────────────────────────────────────────

@router.get("/summary")
async def owner_summary(days: int = 7) -> dict:
    """Daily-ish summary the owner can read in 30 seconds."""
    days = max(1, min(days, 90))
    return summarize_conversions(days=days)


# ── Escalations (human handoff queue) ────────────────────────────────────────

@router.get("/escalations")
async def list_escalations(limit: int = 50) -> list[dict]:
    return list_pending_escalations(limit=max(1, min(limit, 500)))


@router.post("/escalations/{escalation_id}/resolve")
async def resolve_escalation(escalation_id: str) -> dict:
    ok = mark_escalation_resolved(escalation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return {"status": "resolved", "escalation_id": escalation_id}


# ── Eval cases (feedback → eval pipeline) ────────────────────────────────────

@router.post("/cases/harvest")
async def harvest_cases() -> dict:
    """Sweep new thumbs-down feedback into the pending case queue."""
    n = harvest_bad_feedback_to_pending()
    return {"new_pending_cases": n}


@router.get("/cases/pending")
async def pending_cases(limit: int = 50) -> list[dict]:
    return list_pending_cases(limit=max(1, min(limit, 500)))


@router.get("/cases/approved")
async def approved_cases() -> list[dict]:
    return list_approved_cases()


class CaseApproveRequest(BaseModel):
    case_id: str
    expected_intent: str | None = None
    expected_product_ids: list[str] = Field(default_factory=list)
    expected_substring: str | None = None
    must_not_contain: list[str] = Field(default_factory=list)
    notes: str = ""


@router.post("/cases/approve")
async def approve_pending_case(req: CaseApproveRequest) -> dict:
    ok = approve_case(
        case_id=req.case_id,
        expected_intent=req.expected_intent,
        expected_product_ids=req.expected_product_ids or None,
        expected_substring=req.expected_substring,
        must_not_contain=req.must_not_contain or None,
        notes=req.notes,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Pending case not found")
    return {"status": "approved", "case_id": req.case_id}
