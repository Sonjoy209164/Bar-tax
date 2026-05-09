"""
Human handoff (escalation) signaling.

When the bot fails the same customer multiple times in a row, it should stop
guessing and offer to connect them with the shop owner. This module:

  1. Decides when to escalate (consecutive failures, repeated thumbs-down,
     explicit handoff request like "মানুষের সাথে কথা বলব")
  2. Generates the escalation message in the customer's language
  3. Writes a notification record to data/notifications/escalations.jsonl
     so the shop owner can pick up the conversation

The notification log is consumed by:
  - GET /owner/escalations (dashboard)
  - Future: webhook to WhatsApp/Telegram
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.inventory.conversation_state import ConversationState

logger = logging.getLogger(__name__)

_NOTIFICATIONS_PATH = Path("data/notifications/escalations.jsonl")
_FILE_LOCK = threading.Lock()

# Thresholds
CONSECUTIVE_FAILURE_THRESHOLD = 3
THUMBS_DOWN_THRESHOLD = 2

# Explicit "I want a human" phrases
_HANDOFF_PHRASES = (
    "talk to human", "talk to a human", "speak to someone", "real person",
    "human please", "manush", "manusher sathe", "মানুষ", "মানুষের সাথে",
    "owner ke", "owner-er sathe", "boutique e call",
    "actual person", "live agent", "agent",
)


@dataclass(frozen=True)
class EscalationDecision:
    should_escalate: bool
    reason: str | None = None
    message: str | None = None


def decide_escalation(
    *,
    state: ConversationState,
    question: str,
) -> EscalationDecision:
    """
    Decide whether to escalate this turn. Order of checks:
      1. Explicit handoff request → always escalate
      2. Consecutive bot failures → escalate
      3. Repeated thumbs-down → escalate
    """
    if _is_explicit_handoff_request(question):
        return EscalationDecision(
            should_escalate=True,
            reason="explicit_request",
            message=_handoff_message(state, reason="explicit"),
        )

    if state.consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
        return EscalationDecision(
            should_escalate=True,
            reason=f"{state.consecutive_failures}_consecutive_failures",
            message=_handoff_message(state, reason="failures"),
        )

    if state.last_thumbs_down_count >= THUMBS_DOWN_THRESHOLD:
        return EscalationDecision(
            should_escalate=True,
            reason=f"{state.last_thumbs_down_count}_thumbs_down",
            message=_handoff_message(state, reason="thumbs_down"),
        )

    return EscalationDecision(should_escalate=False)


def emit_escalation_notification(
    *,
    state: ConversationState,
    decision: EscalationDecision,
    last_question: str | None = None,
) -> str:
    """
    Append a notification entry. Returns the generated escalation_id.
    Best-effort: returns empty string on failure (caller continues normally).
    """
    if not decision.should_escalate:
        return ""
    try:
        _NOTIFICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        escalation_id = f"ESC-{now[:10].replace('-','')}-{abs(hash(state.session_id + now)) % 100000:05d}"
        entry = {
            "escalation_id": escalation_id,
            "session_id": state.session_id,
            "reason": decision.reason,
            "consecutive_failures": state.consecutive_failures,
            "thumbs_down_count": state.last_thumbs_down_count,
            "last_question": last_question or state.last_question,
            "last_intent": state.last_intent,
            "active_slots": state.active_slots,
            "turn_count": state.turn_count,
            "created_at": now,
            "status": "pending",
        }
        with _FILE_LOCK:
            with _NOTIFICATIONS_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return escalation_id
    except Exception as exc:
        logger.debug("Escalation notification write failed: %s", exc)
        return ""


def list_pending_escalations(limit: int = 50) -> list[dict]:
    """Read pending escalations from the log (for the owner dashboard)."""
    if not _NOTIFICATIONS_PATH.exists():
        return []
    entries: list[dict] = []
    try:
        for line in _NOTIFICATIONS_PATH.read_text(encoding="utf-8").splitlines():
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
        logger.debug("Escalation log read failed: %s", exc)
    return entries[-limit:]


def mark_escalation_resolved(escalation_id: str) -> bool:
    """Mark a single escalation as resolved (rewrite the log)."""
    if not _NOTIFICATIONS_PATH.exists():
        return False
    found = False
    try:
        with _FILE_LOCK:
            entries = []
            for line in _NOTIFICATIONS_PATH.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if entry.get("escalation_id") == escalation_id:
                    entry["status"] = "resolved"
                    entry["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    found = True
                entries.append(entry)
            with _NOTIFICATIONS_PATH.open("w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Escalation resolve failed: %s", exc)
        return False
    return found


def _is_explicit_handoff_request(question: str) -> bool:
    text = question.lower()
    for phrase in _HANDOFF_PHRASES:
        if phrase in text:
            return True
    return False


def _handoff_message(state: ConversationState, reason: str) -> str:
    """Pick a localized escalation message based on the customer's language."""
    lang = (state.active_slots.get("language") if isinstance(state.active_slots, dict) else None) or "english"

    messages = {
        "bangla": (
            "একটু অপেক্ষা করুন — এই বিষয়ে আমাদের boutique-এর staff-এর সাথে "
            "সরাসরি কথা বলার ব্যবস্থা করছি। আপনার phone number দিলে আমরা call করে নেব।"
        ),
        "banglish": (
            "Ektu wait korun — ei bishoye amader boutique-er staff-er sathe "
            "shorashori kotha bolar bebostha korchi. Apnar phone number dile amra call kore neb."
        ),
        "english": (
            "Let me connect you with our boutique team for this. "
            "Could you share your phone number so they can call you back?"
        ),
    }
    return messages.get(lang, messages["english"])
