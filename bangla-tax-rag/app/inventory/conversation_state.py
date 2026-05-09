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

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/conversation/state.sqlite")
_LOCK = threading.RLock()


@dataclass
class ConversationState:
    session_id: str
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
    ) -> ConversationState:
        """Apply a single response's effects to the state and persist."""
        state = self.get(session_id)
        state.turn_count += 1
        state.last_question = question
        state.last_intent = intent
        state.last_shown_product_ids = list(product_ids)
        state.last_primary_product_id = primary_product_id or (
            state.last_shown_product_ids[0] if state.last_shown_product_ids else None
        )
        if slots:
            state.active_slots = {k: v for k, v in slots.items() if v is not None}
            color = slots.get("color_family") or slots.get("color")
            if color:
                state.color_counts[color] = state.color_counts.get(color, 0) + 1
            occ = slots.get("occasion")
            if occ:
                state.occasion_counts[occ] = state.occasion_counts.get(occ, 0) + 1
            cat = slots.get("category_key")
            if cat:
                state.category_counts[cat] = state.category_counts.get(cat, 0) + 1
            budget = slots.get("budget_max")
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


# Module-level singleton (lazy)
_store: ConversationStateStore | None = None


def get_state_store() -> ConversationStateStore:
    global _store
    if _store is None:
        _store = ConversationStateStore()
    return _store
