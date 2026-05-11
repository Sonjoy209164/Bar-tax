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
    trace_id: str | None = None
    confidence_score: float | None = None
    product_ids: list[str] = field(default_factory=list)
    abstained: bool | None = None
    abstention_reason: str | None = None
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
            "trace_id": self.trace_id,
            "confidence_score": self.confidence_score,
            "product_ids": self.product_ids,
            "abstained": self.abstained,
            "abstention_reason": self.abstention_reason,
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
        case = _case_from_feedback_entry(entry, created_at=now)
        new_cases.append(case)

    if not new_cases:
        return 0

    _PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _FILE_LOCK:
        with _PENDING_PATH.open("a", encoding="utf-8") as f:
            for case in new_cases:
                f.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")
    return len(new_cases)


def create_pending_case_from_feedback(entry: dict[str, Any]) -> bool:
    """
    Immediately convert one thumbs-down feedback entry into a pending eval case.

    This is used by the live feedback route so the owner does not need to
    remember to run a separate harvest step before seeing failures.
    """
    if entry.get("rating") != "down":
        return False
    feedback_id = str(entry.get("feedback_id") or "").strip()
    if not feedback_id or feedback_id in _existing_pending_feedback_ids():
        return False

    now = datetime.now(timezone.utc).isoformat()
    case = _case_from_feedback_entry(entry, created_at=now)
    _PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _FILE_LOCK:
        with _PENDING_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")
    return True


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


def evaluate_case_against_response(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate a bot response against one approved feedback-derived case.

    This deliberately uses simple deterministic checks. Feedback should not
    tune the bot by vibes; a reviewer must specify concrete expectations.
    """
    answer = str(response.get("answer") or "")
    normalized_answer = answer.casefold()
    expected_intent = _clean_optional_string(case.get("expected_intent"))
    expected_product_ids = [str(value) for value in case.get("expected_product_ids") or [] if str(value).strip()]
    expected_substring = _clean_optional_string(case.get("expected_substring"))
    must_not_contain = [str(value) for value in case.get("must_not_contain") or [] if str(value).strip()]

    actual_intent = _response_intent(response)
    actual_product_ids = _response_product_ids(response)
    issues: list[str] = []
    checks_run = 0

    if expected_intent:
        checks_run += 1
        if actual_intent != expected_intent:
            issues.append(f"Expected intent {expected_intent!r}, got {actual_intent!r}.")

    if expected_product_ids:
        checks_run += 1
        missing_ids = [product_id for product_id in expected_product_ids if product_id not in actual_product_ids]
        if missing_ids:
            issues.append(f"Missing expected product ids: {', '.join(missing_ids)}.")

    if expected_substring:
        checks_run += 1
        if expected_substring.casefold() not in normalized_answer:
            issues.append(f"Expected answer to contain {expected_substring!r}.")

    for forbidden in must_not_contain:
        checks_run += 1
        if forbidden.casefold() in normalized_answer:
            issues.append(f"Answer must not contain {forbidden!r}.")

    if checks_run == 0:
        issues.append("Approved case has no concrete expectations to check.")

    return {
        "case_id": case.get("case_id"),
        "feedback_id": case.get("feedback_id"),
        "question": case.get("question", ""),
        "passed": not issues,
        "issues": issues,
        "expected": {
            "intent": expected_intent,
            "product_ids": expected_product_ids,
            "substring": expected_substring,
            "must_not_contain": must_not_contain,
        },
        "actual": {
            "intent": actual_intent,
            "product_ids": actual_product_ids,
            "answer_excerpt": answer[:300],
        },
    }


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


def _case_from_feedback_entry(entry: dict[str, Any], *, created_at: str) -> PendingEvalCase:
    feedback_id = str(entry.get("feedback_id") or "")
    return PendingEvalCase(
        case_id=f"CASE-{feedback_id}",
        feedback_id=feedback_id,
        question=entry.get("question", ""),
        bot_answer=entry.get("answer", ""),
        bot_intent=entry.get("intent"),
        user_comment=entry.get("comment"),
        trace_id=entry.get("trace_id"),
        confidence_score=_coerce_float(entry.get("confidence_score")),
        product_ids=_normalize_string_list(entry.get("product_ids", [])),
        abstained=entry.get("abstained") if isinstance(entry.get("abstained"), bool) else None,
        abstention_reason=entry.get("abstention_reason"),
        created_at=created_at,
    )


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


def _clean_optional_string(value: object) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _normalize_string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _response_intent(response: dict[str, Any]) -> str | None:
    answer_plan = response.get("answer_plan")
    if isinstance(answer_plan, dict):
        intent = answer_plan.get("intent") or answer_plan.get("detected_intent")
        if intent:
            return str(intent)
    signals = response.get("signals")
    if isinstance(signals, dict):
        detected = signals.get("detected_intent") or signals.get("intent")
        if detected:
            return str(detected)
    intent = response.get("intent")
    return str(intent) if intent else None


def _response_product_ids(response: dict[str, Any]) -> list[str]:
    ids: list[str] = []

    def add(values: object) -> None:
        if not isinstance(values, list):
            return
        for value in values:
            product_id = str(value).strip()
            if product_id and product_id not in ids:
                ids.append(product_id)

    add(response.get("recommended_product_ids"))
    add(response.get("cross_sell_product_ids"))
    hits = response.get("hits")
    if isinstance(hits, list):
        for hit in hits:
            if isinstance(hit, dict):
                product_id = str(hit.get("product_id") or "").strip()
                if product_id and product_id not in ids:
                    ids.append(product_id)
    answer_plan = response.get("answer_plan")
    if isinstance(answer_plan, dict):
        primary = answer_plan.get("primary_product_id")
        if primary and str(primary) not in ids:
            ids.append(str(primary))
        add(answer_plan.get("alternative_product_ids"))
        add(answer_plan.get("cross_sell_product_ids"))
    return ids


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
