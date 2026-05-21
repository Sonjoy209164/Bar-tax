"""
Structured conversation state for the boutique chatbot.

Replaces the old "concatenate last 3 user turns into a string" approach with
a real stateful object that tracks what the bot last showed, what intent it
last handled, and what slots are still active.

This is the foundation for:
  - coreference resolution ("এটা", "ওটা", "first one")
  - preference learning (count repeated colors / occasions / budget bands)
  - escalation (track consecutive failures)
  - personalization (active slots carry over without re-extraction)

Storage is SQLite (single file, no external service) so state survives
process restarts. Falls back to in-memory dict if the DB can't be opened.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.inventory.memory_policy import (
    default_product_focus_ttl,
    filter_safe_slots_for_memory,
    product_focus_expires_at,
    should_write_memory,
    to_iso,
)

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/conversation/state.sqlite")
_LOCK = threading.RLock()


@dataclass
class ConversationState:
    session_id: str
    schema_version: int = 2
    last_shown_product_ids: list[str] = field(default_factory=list)
    last_primary_product_id: str | None = None
    last_intent: str | None = None
    last_question: str | None = None
    active_slots: dict[str, Any] = field(default_factory=dict)
    clarification_pending: str | None = None  # which slot the bot just asked about
    turn_count: int = 0
    consecutive_failures: int = 0  # abstained or low-confidence in a row
    color_counts: dict[str, int] = field(default_factory=dict)
    occasion_counts: dict[str, int] = field(default_factory=dict)
    budget_observations: list[float] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)
    last_thumbs_down_count: int = 0
    updated_at: str = ""
    product_focus_source: str | None = None
    product_focus_updated_at: str | None = None
    product_focus_expires_at: str | None = None
    product_focus_confidence: float = 0.0
    product_focus_ttl_seconds: int = 0
    product_focus_write_reason: str | None = None
    product_focus_last_used_at: str | None = None
    product_focus_use_count: int = 0
    slot_memory_meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str, session_id: str) -> "ConversationState":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return cls(session_id=session_id)
        # Defensive: only pull known fields
        kwargs: dict[str, Any] = {"session_id": session_id}
        for f_name in cls.__dataclass_fields__:  # type: ignore[attr-defined]
            if f_name in data:
                kwargs[f_name] = data[f_name]
        return cls(**kwargs)


class ConversationStateStore:
    """SQLite-backed store with in-memory fallback."""

    def __init__(self, db_path: Path | str = _DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._memory: dict[str, ConversationState] = {}
        self._memory_only = False
        try:
            self._init_db()
        except Exception as exc:
            logger.warning("ConversationStateStore: SQLite init failed (%s) — using in-memory", exc)
            self._memory_only = True

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_state (
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_updated ON conversation_state(updated_at)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get(self, session_id: str) -> ConversationState:
        if not session_id:
            return ConversationState(session_id="")
        with _LOCK:
            if self._memory_only:
                return self._memory.get(session_id) or ConversationState(session_id=session_id)
            try:
                with self._connect() as conn:
                    row = conn.execute(
                        "SELECT payload FROM conversation_state WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                if row is None:
                    return ConversationState(session_id=session_id)
                return ConversationState.from_json(row["payload"], session_id=session_id)
            except Exception as exc:
                logger.debug("ConversationState read failed: %s", exc)
                return ConversationState(session_id=session_id)

    def save(self, state: ConversationState) -> None:
        if not state.session_id:
            return
        state.updated_at = datetime.now(timezone.utc).isoformat()
        with _LOCK:
            if self._memory_only:
                self._memory[state.session_id] = state
                return
            try:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO conversation_state(session_id, payload, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(session_id) DO UPDATE SET
                            payload = excluded.payload,
                            updated_at = excluded.updated_at
                        """,
                        (state.session_id, state.to_json(), state.updated_at),
                    )
            except Exception as exc:
                logger.debug("ConversationState write failed: %s", exc)
                self._memory[state.session_id] = state

    def clear(self, session_id: str) -> None:
        with _LOCK:
            self._memory.pop(session_id, None)
            if self._memory_only:
                return
            try:
                with self._connect() as conn:
                    conn.execute(
                        "DELETE FROM conversation_state WHERE session_id = ?",
                        (session_id,),
                    )
            except Exception:
                pass

    # Update helpers — applied after every turn

    def record_turn(
        self,
        *,
        session_id: str,
        question: str,
        intent: str,
        slots: dict[str, Any] | None,
        product_ids: list[str],
        primary_product_id: str | None,
        confidence: float,
        abstained: bool,
        clarification_pending: str | None = None,
        memory_source: str | None = None,
        memory_confidence: float | None = None,
        ttl_seconds: int | None = None,
        write_reason: str | None = None,
    ) -> ConversationState:
        """Apply a single response's effects to the state and persist."""
        state = self.get(session_id)
        state.turn_count += 1
        state.last_question = question
        state.last_intent = intent

        write_decision = should_write_memory(
            intent=intent,
            slots=slots,
            product_ids=product_ids,
            primary_product_id=primary_product_id,
            confidence=confidence,
            abstained=abstained,
        )
        safe_slots = (
            filter_safe_slots_for_memory(intent=intent, slots=slots)
            if write_decision.allowed
            else {}
        )

        if write_decision.allowed:
            if product_ids:
                state.last_shown_product_ids = list(product_ids)
                state.last_primary_product_id = primary_product_id or (
                    state.last_shown_product_ids[0] if state.last_shown_product_ids else None
                )
                self._write_product_focus_meta(
                    state=state,
                    intent=intent,
                    memory_source=memory_source,
                    confidence=memory_confidence if memory_confidence is not None else confidence,
                    ttl_seconds=ttl_seconds,
                    write_reason=write_reason or write_decision.reason,
                )
            elif primary_product_id:
                state.last_primary_product_id = primary_product_id
                self._write_product_focus_meta(
                    state=state,
                    intent=intent,
                    memory_source=memory_source,
                    confidence=memory_confidence if memory_confidence is not None else confidence,
                    ttl_seconds=ttl_seconds,
                    write_reason=write_reason or write_decision.reason,
                )

        if safe_slots:
            incoming_slots = {k: v for k, v in safe_slots.items() if v is not None}
            previous_category = state.active_slots.get("category_key")
            incoming_category = incoming_slots.get("category_key")
            if (
                incoming_category
                and previous_category
                and incoming_category != previous_category
            ):
                keep = {
                    key: value
                    for key, value in state.active_slots.items()
                    if key in {"budget_min", "budget_max", "language"}
                }
                state.active_slots = {**keep, **incoming_slots}
            else:
                state.active_slots = {**state.active_slots, **incoming_slots}
            self._write_slot_meta(
                state=state,
                slots=incoming_slots,
                memory_source=memory_source or self._infer_memory_source(intent),
                confidence=memory_confidence if memory_confidence is not None else confidence,
                ttl_seconds=ttl_seconds or default_product_focus_ttl(intent),
                write_reason=write_reason or write_decision.reason,
            )
            color = incoming_slots.get("color_family") or incoming_slots.get("color")
            if color:
                state.color_counts[color] = state.color_counts.get(color, 0) + 1
            occ = incoming_slots.get("occasion")
            if occ:
                state.occasion_counts[occ] = state.occasion_counts.get(occ, 0) + 1
            cat = incoming_slots.get("category_key")
            if cat:
                state.category_counts[cat] = state.category_counts.get(cat, 0) + 1
            budget = incoming_slots.get("budget_max")
            if isinstance(budget, (int, float)) and budget > 0:
                state.budget_observations.append(float(budget))
                state.budget_observations = state.budget_observations[-10:]
        if abstained or confidence < 0.5:
            state.consecutive_failures += 1
        else:
            state.consecutive_failures = 0
        state.clarification_pending = clarification_pending
        self.save(state)
        return state

    @staticmethod
    def _infer_memory_source(intent: str) -> str:
        normalized = (intent or "").strip().casefold()
        if normalized == "image_search":
            return "image_search"
        if normalized.startswith("occasion_") or normalized in {"gift_recommendation", "vague_shopping"}:
            return "polite_boundary"
        if "order" in normalized or "cart" in normalized:
            return "order_flow"
        return "text_search"

    def _write_product_focus_meta(
        self,
        *,
        state: ConversationState,
        intent: str,
        memory_source: str | None,
        confidence: float,
        ttl_seconds: int | None,
        write_reason: str,
    ) -> None:
        now = to_iso()
        ttl = ttl_seconds or default_product_focus_ttl(intent)
        state.product_focus_source = memory_source or self._infer_memory_source(intent)
        state.product_focus_updated_at = now
        state.product_focus_ttl_seconds = int(ttl)
        state.product_focus_expires_at = product_focus_expires_at(
            updated_at=now,
            ttl_seconds=int(ttl),
        )
        state.product_focus_confidence = float(max(0.0, min(1.0, confidence)))
        state.product_focus_write_reason = write_reason
        state.product_focus_last_used_at = None
        state.product_focus_use_count = 0

    @staticmethod
    def _write_slot_meta(
        *,
        state: ConversationState,
        slots: dict[str, Any],
        memory_source: str,
        confidence: float,
        ttl_seconds: int,
        write_reason: str,
    ) -> None:
        now = to_iso()
        expires_at = product_focus_expires_at(updated_at=now, ttl_seconds=ttl_seconds)
        for key in slots:
            state.slot_memory_meta[key] = {
                "memory_source": memory_source,
                "updated_at": now,
                "expires_at": expires_at,
                "confidence": float(max(0.0, min(1.0, confidence))),
                "ttl_seconds": int(ttl_seconds),
                "write_reason": write_reason,
            }


# Module-level singleton (lazy)
_store: ConversationStateStore | None = None


def get_state_store() -> ConversationStateStore:
    global _store
    if _store is None:
        _store = ConversationStateStore()
    return _store
