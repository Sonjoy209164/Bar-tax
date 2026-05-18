from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/identity.sqlite")
_SESSION_MAP_PATH = Path("data/session_phone_map.json")


def _ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_profiles (
            phone TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_map (
            session_id TEXT PRIMARY KEY,
            phone TEXT NOT NULL,
            linked_at TEXT NOT NULL
        )
    """)
    conn.commit()


@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        _ensure_db(conn)
        yield conn
    finally:
        conn.close()


class IdentityStore:
    """Persistent cross-session customer identity backed by SQLite.

    A customer is identified by their phone number.  A session_id (browser
    random string) is linked to a phone number as soon as the customer shares
    their phone (either while ordering or explicitly).  After linking, all
    future sessions with the same phone recover the same profile.
    """

    # ── Profile CRUD ────────────────────────────────────────────────────────

    def get_profile(self, phone: str) -> dict[str, Any] | None:
        with _db() as conn:
            row = conn.execute(
                "SELECT profile_json FROM customer_profiles WHERE phone = ?", (phone,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["profile_json"])
        except json.JSONDecodeError:
            return None

    def upsert_profile(self, phone: str, profile: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        profile_json = json.dumps(profile, ensure_ascii=False)
        with _db() as conn:
            existing = conn.execute(
                "SELECT created_at FROM customer_profiles WHERE phone = ?", (phone,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE customer_profiles SET profile_json = ?, updated_at = ? WHERE phone = ?",
                    (profile_json, now, phone),
                )
            else:
                conn.execute(
                    "INSERT INTO customer_profiles (phone, profile_json, created_at, updated_at) VALUES (?,?,?,?)",
                    (phone, profile_json, now, now),
                )
            conn.commit()

    def delete_profile(self, phone: str) -> bool:
        with _db() as conn:
            cursor = conn.execute("DELETE FROM customer_profiles WHERE phone = ?", (phone,))
            conn.commit()
            return cursor.rowcount > 0

    # ── Session → Phone mapping ─────────────────────────────────────────────

    def link_session(self, session_id: str, phone: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO session_map (session_id, phone, linked_at) VALUES (?,?,?)",
                (session_id, phone, now),
            )
            conn.commit()
        logger.debug("Linked session %s to phone %s", session_id, phone[-4:])

    def get_phone_for_session(self, session_id: str) -> str | None:
        with _db() as conn:
            row = conn.execute(
                "SELECT phone FROM session_map WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row["phone"] if row else None

    def get_or_create_profile(self, session_id: str, phone: str | None = None) -> dict[str, Any]:
        """
        Resolve a profile for a session. Resolution order:
        1. If phone provided → link session → load/create profile for that phone
        2. If session already linked → load profile for linked phone
        3. Otherwise → return empty profile (not persisted yet)
        """
        effective_phone = phone
        if not effective_phone:
            effective_phone = self.get_phone_for_session(session_id)

        if effective_phone:
            if phone:
                self.link_session(session_id, effective_phone)
            profile = self.get_profile(effective_phone)
            if profile is None:
                return {"phone": effective_phone, "session_id": session_id}
            return profile

        # No phone known — return transient profile
        return {"session_id": session_id}

    def save_session_profile(self, session_id: str, profile: dict[str, Any]) -> bool:
        """Persist profile if we have a phone linked to this session."""
        phone = profile.get("phone") or self.get_phone_for_session(session_id)
        if not phone:
            return False
        if profile.get("phone") and phone != self.get_phone_for_session(session_id):
            self.link_session(session_id, phone)
        self.upsert_profile(phone, profile)
        return True

    # ── Analytics helpers ───────────────────────────────────────────────────

    def known_customer_count(self) -> int:
        with _db() as conn:
            row = conn.execute("SELECT COUNT(*) as n FROM customer_profiles").fetchone()
        return row["n"] if row else 0

    def recent_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with _db() as conn:
            rows = conn.execute(
                "SELECT session_id, phone, linked_at FROM session_map ORDER BY linked_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
