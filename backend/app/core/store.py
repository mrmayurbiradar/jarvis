"""SQLite-backed durable stores: pairings, sessions, memory, audit, tasks.

* Append-only audit log (matrix row C5).
* Worker tokens are stored hashed (sha256); verification is constant-time
  (ADR-0005).
* SQLite via stdlib — the local-only mode needs no containers (ADR-0004).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS pairings (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  token_hash TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  approved_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  messages TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS memory_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  fact TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  capability TEXT NOT NULL,
  target TEXT NOT NULL DEFAULT '',
  decision TEXT NOT NULL,
  outcome TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), expected_hash)


class Store:
    """Thread-safe wrapper over SQLite. Local-only backend for now."""

    def __init__(self, db_path: Path, *, ttl_seconds: int = 600) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds
        with self._lock, self._conn:
            self._conn.executescript(SCHEMA)

    # --- pairing / worker tokens (ADR-0005 gate 1) ---

    def request_pairing(self, display_name: str) -> dict[str, str]:
        pairing_id = uuid.uuid4().hex
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = _now()
        expires = (
            datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        ).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO pairings (id, display_name, code, status, token_hash,"
                " created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
                (pairing_id, display_name, code, "pending", "", now, expires),
            )
        return {"pairing_id": pairing_id, "code": code, "expires_at": expires}

    def confirm_pairing(self, code: str) -> str | None:
        """Approve a pending pairing and issue a worker token. Returns None if
        the code is unknown, expired, or already used."""
        now = _now()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM pairings WHERE code=? AND status='pending'", (code,)
            ).fetchone()
            if row is None or row["expires_at"] < now:
                return None
            token = secrets.token_urlsafe(32)
            self._conn.execute(
                "UPDATE pairings SET status='approved', token_hash=?, approved_at=?"
                " WHERE id=?",
                (hash_token(token), now, row["id"]),
            )
        return token

    def verify_worker_token(self, token: str) -> bool:
        if not token:
            return False
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT token_hash FROM pairings WHERE status='approved'", ()
            ).fetchall()
        return any(tokens_match(token, r["token_hash"]) for r in rows)

    def revoke_worker(self, token: str) -> bool:
        """Revoke a worker token; immediately invalidates commands (ADR-0005)."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE pairings SET status='revoked' WHERE token_hash=? AND status='approved'",
                (hash_token(token),),
            )
            return cur.rowcount > 0

    # --- sessions (conversation history) ---

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT messages FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        if row is None:
            return []
        try:
            return json.loads(row["messages"])
        except (TypeError, ValueError):
            return []

    def append_session_messages(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions (id, created_at, updated_at, messages) VALUES (?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET messages=excluded.messages,"
                " updated_at=excluded.updated_at",
                (session_id, now, now, json.dumps(messages)),
            )

    # --- memory (long-term, scoped) ---

    def save_memory(self, session_id: str, fact: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO memory_entries (session_id, fact, created_at) VALUES (?,?,?)",
                (session_id, fact, _now()),
            )

    def recall_memory(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, session_id, fact, created_at FROM memory_entries"
                " WHERE fact LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- audit log (append-only) ---

    def append_audit(
        self,
        *,
        actor: str,
        capability: str,
        target: str = "",
        decision: str = "allow",
        outcome: str = "ok",
        reason: str = "",
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO audit_log (ts, actor, capability, target, decision,"
                " outcome, reason) VALUES (?,?,?,?,?,?,?)",
                (_now(), actor, capability, target, decision, outcome, reason),
            )

    def list_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT ts, actor, capability, target, decision, outcome, reason"
                " FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- task state (durable jobs) ---

    def create_task(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO tasks (id, kind, status, payload, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (task_id, kind, "queued", json.dumps(payload), now, now),
            )
        return {"id": task_id, "kind": kind, "status": "queued", "payload": payload, "created_at": now}

    def set_task_status(self, task_id: str, status: str) -> None:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE id=?", (status, _now(), task_id)
            )
            if cur.rowcount == 0:
                raise KeyError(task_id)