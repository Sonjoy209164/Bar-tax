"""
Feedback → Eval-case pipeline.

Closes the loop between bad-rating user feedback and the eval suite:

  customer thumbs-down  ──►  feedback.jsonl
                              │
                              ▼ (this module)
                         pending_cases.jsonl  ──►  shop owner reviews & approves
                                                        │
                                                        ▼
                                                 approved_cases.jsonl  ──►  eval suite

The shop owner can review pending cases via /owner/pending-cases and approve
them. Approved cases are stable test fixtures the bot must continue to pass.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FEEDBACK_PATH = Path("data/feedback/feedback.jsonl")
_PENDING_PATH = Path("data/eval/pending_cases.jsonl")
_APPROVED_PATH = Path("data/eval/approved_cases.jsonl")

_FILE_LOCK = threading.Lock()


@dataclass
class PendingEvalCase:
    case_id: str
    feedback_id: str
    question: str
    bot_answer: str
    bot_intent: str | None
    user_comment: str | None
    expected_intent: str | None = None      # filled in by reviewer
    expected_product_ids: list[str] = field(default_factory=list)
    expected_substring: str | None = None    # text the answer must contain
    must_not_contain: list[str] = field(default_factory=list)
    notes: str = ""
    status: str = "pending"  # pending | approved | rejected
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "feedback_id": self.feedback_id,
            "question": self.question,
            "bot_answer": self.bot_answer,
            "bot_intent": self.bot_intent,
            "user_comment": self.user_comment,
            "expected_intent": self.expected_intent,
            "expected_product_ids": self.expected_product_ids,
            "expected_substring": self.expected_substring,
            "must_not_contain": self.must_not_contain,
            "notes": self.notes,
            "status": self.status,
            "created_at": self.created_at,
        }


def harvest_bad_feedback_to_pending() -> int:
    """
    Read all thumbs-down entries from feedback.jsonl and write any not yet
    captured to pending_cases.jsonl. Idempotent — uses feedback_id as the
    de-dup key.

    Returns the number of new pending cases created.
    """
    if not _FEEDBACK_PATH.exists():
        return 0

    bad_entries = _read_thumbs_down_entries()
    existing_ids = _existing_pending_feedback_ids()

    new_cases: list[PendingEvalCase] = []
    now = datetime.now(timezone.utc).isoformat()
    for entry in bad_entries:
        fb_id = entry.get("feedback_id") or ""
        if not fb_id or fb_id in existing_ids:
            continue
        case_id = f"CASE-{fb_id}"
        case = PendingEvalCase(
            case_id=case_id,
            feedback_id=fb_id,
            question=entry.get("question", ""),
            bot_answer=entry.get("answer", ""),
            bot_intent=entry.get("intent"),
            user_comment=entry.get("comment"),
            created_at=now,
        )
        new_cases.append(case)

    if not new_cases:
        return 0

    _PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _FILE_LOCK:
        with _PENDING_PATH.open("a", encoding="utf-8") as f:
            for case in new_cases:
                f.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")
    return len(new_cases)


def list_pending_cases(limit: int = 50) -> list[dict[str, Any]]:
    if not _PENDING_PATH.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in _PENDING_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
                if entry.get("status") == "pending":
                    entries.append(entry)
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        logger.debug("Pending case read failed: %s", exc)
    return entries[-limit:]


def approve_case(
    *,
    case_id: str,
    expected_intent: str | None = None,
    expected_product_ids: list[str] | None = None,
    expected_substring: str | None = None,
    must_not_contain: list[str] | None = None,
    notes: str = "",
) -> bool:
    """
    Move a pending case to approved with the reviewer's annotations.
    Returns True on success.
    """
    if not _PENDING_PATH.exists():
        return False
    found = False
    approved_payload: dict[str, Any] | None = None
    try:
        with _FILE_LOCK:
            remaining: list[dict[str, Any]] = []
            for line in _PENDING_PATH.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if entry.get("case_id") == case_id and entry.get("status") == "pending":
                    entry["status"] = "approved"
                    entry["approved_at"] = datetime.now(timezone.utc).isoformat()
                    if expected_intent is not None:
                        entry["expected_intent"] = expected_intent
                    if expected_product_ids is not None:
                        entry["expected_product_ids"] = expected_product_ids
                    if expected_substring is not None:
                        entry["expected_substring"] = expected_substring
                    if must_not_contain is not None:
                        entry["must_not_contain"] = must_not_contain
                    if notes:
                        entry["notes"] = notes
                    found = True
                    approved_payload = entry
                else:
                    remaining.append(entry)

            # Rewrite pending file (without approved entry)
            with _PENDING_PATH.open("w", encoding="utf-8") as f:
                for e in remaining:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")

            # Append to approved file
            if approved_payload is not None:
                _APPROVED_PATH.parent.mkdir(parents=True, exist_ok=True)
                with _APPROVED_PATH.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(approved_payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Case approval failed: %s", exc)
        return False
    return found


def list_approved_cases() -> list[dict[str, Any]]:
    if not _APPROVED_PATH.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in _APPROVED_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        logger.debug("Approved case read failed: %s", exc)
    return entries


def _read_thumbs_down_entries() -> list[dict[str, Any]]:
    if not _FEEDBACK_PATH.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in _FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
            if entry.get("rating") == "down":
                out.append(entry)
        except json.JSONDecodeError:
            continue
    return out


def _existing_pending_feedback_ids() -> set[str]:
    ids: set[str] = set()
    for path in (_PENDING_PATH, _APPROVED_PATH):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
                fb_id = entry.get("feedback_id")
                if fb_id:
                    ids.add(fb_id)
            except json.JSONDecodeError:
                continue
    return ids
