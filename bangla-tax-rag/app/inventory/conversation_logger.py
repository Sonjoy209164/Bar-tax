"""
Append-only sink for real off-topic / boundary traffic.

Why this exists: the regex/keyword logic is brittle precisely because it was
authored from imagination, not from customer messages. This logger captures
every boundary trigger so the next iteration is grounded in actual usage.

Output: `data/conversation_logs/raw_offtopic.jsonl` (one JSON object per line).
PII (digit runs that look like phone numbers, emails) is masked before write.

The logger never raises — failure to log must not break the user's reply.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "conversation_logs" / "raw_offtopic.jsonl"
_PATH_ENV = "BOUNDARY_LOG_PATH"

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b\d{7,}\b")
_ORDER_ID_RE = re.compile(r"\b(?:ORD|ORDER|INV)[-_ ]?\d{3,}\b", re.IGNORECASE)

_lock = Lock()


def log_boundary_trigger(
    *,
    question: str,
    language: str,
    boundary_type: str,
    confidence: float,
    risk_level: str,
    allowed_action: str,
    source: str,
    handoff_recommended: bool,
    slots: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Append one row to the boundary log. Swallow all errors."""
    try:
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "question": _redact(question),
            "language": language,
            "boundary_type": boundary_type,
            "confidence": round(float(confidence), 3),
            "risk_level": risk_level,
            "allowed_action": allowed_action,
            "source": source,
            "handoff_recommended": handoff_recommended,
            "slots": {k: v for k, v in (slots or {}).items() if v is not None and v != ""},
        }
        path = _resolve_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False)
        with _lock, path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as exc:  # pragma: no cover — log-and-continue
        logger.debug("boundary logger failed: %s", exc)


def _resolve_path() -> Path:
    override = os.environ.get(_PATH_ENV)
    return Path(override) if override else _DEFAULT_PATH


def _redact(text: str) -> str:
    redacted = _EMAIL_RE.sub("[EMAIL]", text)
    redacted = _ORDER_ID_RE.sub("[ORDER_ID]", redacted)
    redacted = _PHONE_RE.sub("[NUMBER]", redacted)
    return redacted


__all__ = ["log_boundary_trigger"]
