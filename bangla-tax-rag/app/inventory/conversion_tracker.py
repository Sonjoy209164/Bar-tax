"""
Conversion funnel tracking.

Logs three event types so the owner can see what's working:

  - "shown"   — bot displayed a product to a customer
  - "ordered" — customer placed an order containing the product
  - "abstain" — bot couldn't answer the question

Pure append-only JSONL so it's safe to read without locking. Aggregation
lives in `summarize_conversions` which is what the dashboard calls.

The stream powers two questions:
  1. "Which products get a lot of attention but never sell?" (drop-off)
  2. "Which questions does the bot fail on?" (abstention rate)
"""
from __future__ import annotations

import json
import logging
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_LOG_PATH = Path("data/analytics/conversions.jsonl")
_FILE_LOCK = threading.Lock()


def record_shown(
    *,
    session_id: str,
    question: str,
    product_ids: Iterable[str],
    intent: str,
    confidence: float,
) -> None:
    """Bot showed these products in response to this question."""
    _write_event({
        "event": "shown",
        "session_id": session_id,
        "question": question,
        "product_ids": list(product_ids),
        "intent": intent,
        "confidence": round(confidence, 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def record_abstain(
    *,
    session_id: str,
    question: str,
    intent: str,
    reason: str | None,
) -> None:
    """Bot couldn't answer — logged so we can surface failed questions."""
    _write_event({
        "event": "abstain",
        "session_id": session_id,
        "question": question,
        "intent": intent,
        "reason": reason or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def record_ordered(
    *,
    session_id: str,
    order_id: str,
    product_ids: Iterable[str],
    total_amount: float | None = None,
) -> None:
    """Customer placed an order — links session_id back to earlier 'shown' events."""
    _write_event({
        "event": "ordered",
        "session_id": session_id,
        "order_id": order_id,
        "product_ids": list(product_ids),
        "total_amount": total_amount,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def summarize_conversions(days: int = 7) -> dict[str, Any]:
    """
    Aggregate the funnel for the last `days` days.

    Returns:
      {
        "shown_total": int,
        "ordered_total": int,
        "abstain_total": int,
        "conversion_rate": float | None,        # ordered / shown
        "abstain_rate": float | None,           # abstain / (shown + abstain)
        "top_shown_products": [(product_id, count), ...],
        "top_ordered_products": [(product_id, count), ...],
        "drop_off_products": [{ product_id, shown, ordered, ratio }, ...],
        "failed_questions_sample": [...],
      }
    """
    if not _LOG_PATH.exists():
        return _empty_summary()

    cutoff = _cutoff_iso(days)
    shown_count = 0
    ordered_count = 0
    abstain_count = 0
    shown_per_product: Counter = Counter()
    ordered_per_product: Counter = Counter()
    failed_questions: list[dict[str, Any]] = []
    sessions_with_shown: dict[str, set[str]] = defaultdict(set)
    sessions_with_order: dict[str, set[str]] = defaultdict(set)

    for entry in _iter_events():
        ts = entry.get("timestamp", "")
        if ts < cutoff:
            continue
        event = entry.get("event")
        if event == "shown":
            shown_count += 1
            for pid in entry.get("product_ids", []):
                shown_per_product[pid] += 1
                sessions_with_shown[pid].add(entry.get("session_id", ""))
        elif event == "ordered":
            ordered_count += 1
            for pid in entry.get("product_ids", []):
                ordered_per_product[pid] += 1
                sessions_with_order[pid].add(entry.get("session_id", ""))
        elif event == "abstain":
            abstain_count += 1
            failed_questions.append({
                "question": entry.get("question", ""),
                "intent": entry.get("intent"),
                "reason": entry.get("reason"),
                "timestamp": ts,
            })

    # Drop-off — products shown a lot but rarely ordered (within same session)
    drop_off: list[dict[str, Any]] = []
    for pid, shown in shown_per_product.most_common(20):
        ordered_for_pid = sum(
            1 for sess in sessions_with_shown[pid] if sess in sessions_with_order.get(pid, set())
        )
        if shown >= 3:
            ratio = ordered_for_pid / shown if shown else 0.0
            drop_off.append({
                "product_id": pid,
                "shown_in_sessions": len(sessions_with_shown[pid]),
                "ordered_in_sessions": ordered_for_pid,
                "session_conversion_ratio": round(ratio, 3),
            })
    drop_off.sort(key=lambda d: d["session_conversion_ratio"])

    return {
        "window_days": days,
        "shown_total": shown_count,
        "ordered_total": ordered_count,
        "abstain_total": abstain_count,
        "conversion_rate": round(ordered_count / shown_count, 3) if shown_count else None,
        "abstain_rate": (
            round(abstain_count / (shown_count + abstain_count), 3)
            if (shown_count + abstain_count) else None
        ),
        "top_shown_products": shown_per_product.most_common(10),
        "top_ordered_products": ordered_per_product.most_common(10),
        "drop_off_products": drop_off[:10],
        "failed_questions_sample": failed_questions[-20:],
    }


def _write_event(entry: dict[str, Any]) -> None:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _FILE_LOCK:
            with _LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Conversion event write failed: %s", exc)


def _iter_events() -> Iterable[dict[str, Any]]:
    if not _LOG_PATH.exists():
        return
    for line in _LOG_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            continue


def _cutoff_iso(days: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _empty_summary() -> dict[str, Any]:
    return {
        "window_days": 0,
        "shown_total": 0,
        "ordered_total": 0,
        "abstain_total": 0,
        "conversion_rate": None,
        "abstain_rate": None,
        "top_shown_products": [],
        "top_ordered_products": [],
        "drop_off_products": [],
        "failed_questions_sample": [],
    }
