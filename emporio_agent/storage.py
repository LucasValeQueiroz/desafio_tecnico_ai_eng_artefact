"""Local persistence: conversations, an audit trail per turn, and tickets for the team."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    messages_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    failed_verifications INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    user_text TEXT NOT NULL,
    reply TEXT NOT NULL,
    tool_trace_json TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    guard_flags_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    protocol TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    customer_name TEXT,
    contact TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);
"""


@dataclass
class SessionState:
    id: str
    provider: str
    model: str
    messages: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    failed_verifications: int = 0


class Storage:
    def __init__(self, path: Path) -> None:
        self._path = str(path)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self._path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def load_session(self, session_id: str, provider: str, model: str) -> SessionState:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return SessionState(session_id, provider, model)
        if row["provider"] != provider:
            # History is stored in the provider's native format, so it can't cross providers.
            raise ValueError(f"Session '{session_id}' belongs to provider '{row['provider']}'.")
        return SessionState(
            id=row["id"],
            provider=row["provider"],
            model=row["model"],
            messages=json.loads(row["messages_json"]),
            evidence=json.loads(row["evidence_json"]),
            failed_verifications=row["failed_verifications"],
        )

    def save_session(self, state: SessionState) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO sessions (id, provider, model, created_at, updated_at, messages_json, evidence_json, failed_verifications)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    messages_json = excluded.messages_json,
                    evidence_json = excluded.evidence_json,
                    failed_verifications = MAX(sessions.failed_verifications, excluded.failed_verifications)
                """,
                (
                    state.id, state.provider, state.model, now, now,
                    json.dumps(state.messages, ensure_ascii=False),
                    json.dumps(state.evidence, ensure_ascii=False),
                    state.failed_verifications,
                ),
            )

    def record_failed_verification(self, state: SessionState) -> None:
        """Persist immediately, so that a failed turn can't reset the lockout counter."""
        state.failed_verifications += 1
        self.save_session(
            SessionState(state.id, state.provider, state.model, state.messages, state.evidence, state.failed_verifications)
        )

    def record_turn(
        self,
        session_id: str,
        user_text: str,
        reply: str,
        tool_trace: list[dict],
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        guard_flags: list[str],
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO turns (session_id, created_at, user_text, reply, tool_trace_json, latency_ms, input_tokens, output_tokens, guard_flags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, datetime.now(UTC).isoformat(timespec="seconds"), user_text, reply,
                    json.dumps(tool_trace, ensure_ascii=False), latency_ms, input_tokens, output_tokens,
                    json.dumps(guard_flags, ensure_ascii=False),
                ),
            )

    def create_ticket(self, session_id: str, kind: str, summary: str, customer_name: str | None, contact: str | None, now: datetime) -> str:
        with self._connect() as db:
            # Take the write lock before counting, so that concurrent turns get distinct protocols.
            db.execute("BEGIN IMMEDIATE")
            sequence = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] + 1
            protocol = f"EM-{now:%Y%m%d}-{sequence:04d}"
            db.execute(
                "INSERT INTO tickets (protocol, session_id, kind, summary, customer_name, contact, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (protocol, session_id, kind, summary, customer_name, contact, now.isoformat(timespec="seconds")),
            )
        return protocol

    def tickets(self) -> list[dict]:
        with self._connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM tickets ORDER BY created_at").fetchall()]

    def turns(self, session_id: str) -> list[dict]:
        with self._connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM turns WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()]
