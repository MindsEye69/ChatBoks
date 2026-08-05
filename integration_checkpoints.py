"""Durable, fail-closed checkpoint receipts for isolated integration workers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid


_SCHEMA_VERSION = 1
_MAX_IDENTIFIER_CHARS = 128
_STATES = {"prepared", "in_progress", "completed", "uncertain"}
_PLAN = {
    "schema": "chatboks.execution-checkpoint/v1",
    "steps": [{"id": "agent_execute", "reversibility": "unknown"}],
}


class IntegrationCheckpointError(ValueError):
    """A checkpoint cannot safely transition or be replayed."""


@dataclass(frozen=True)
class IntegrationCheckpoint:
    execution_id: str
    request_id: str
    state: str
    plan_digest: str
    created_at: str
    updated_at: str
    step_started_at: str | None
    completed_at: str | None
    result_status: str | None
    result_digest: str | None
    recovery_reason: str | None


def default_checkpoint_registry_path(project_path: Path) -> Path:
    return project_path / ".chatboks" / "integration-checkpoints.sqlite3"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise IntegrationCheckpointError(f"{label} must be a bounded string.")
    value = value.strip()
    if not value or len(value) > _MAX_IDENTIFIER_CHARS:
        raise IntegrationCheckpointError(f"{label} must be a bounded string.")
    return value


class IntegrationCheckpointRegistry:
    """One durable receipt chain per isolated execution; never auto-replays work."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._transaction() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > _SCHEMA_VERSION:
                raise IntegrationCheckpointError("Checkpoint schema is newer than this ChatBoks version supports.")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS integration_checkpoints (
                    execution_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL CHECK(state IN ('prepared', 'in_progress', 'completed', 'uncertain')),
                    plan_digest TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    step_started_at TEXT, completed_at TEXT, result_status TEXT, result_digest TEXT,
                    recovery_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS integration_checkpoint_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                    execution_id TEXT NOT NULL, occurred_at TEXT NOT NULL, event_type TEXT NOT NULL,
                    FOREIGN KEY(execution_id) REFERENCES integration_checkpoints(execution_id)
                );
                """
            )
            if version < _SCHEMA_VERSION:
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> IntegrationCheckpoint:
        return IntegrationCheckpoint(
            execution_id=str(row["execution_id"]), request_id=str(row["request_id"]), state=str(row["state"]),
            plan_digest=str(row["plan_digest"]), created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
            step_started_at=str(row["step_started_at"]) if row["step_started_at"] is not None else None,
            completed_at=str(row["completed_at"]) if row["completed_at"] is not None else None,
            result_status=str(row["result_status"]) if row["result_status"] is not None else None,
            result_digest=str(row["result_digest"]) if row["result_digest"] is not None else None,
            recovery_reason=str(row["recovery_reason"]) if row["recovery_reason"] is not None else None,
        )

    @staticmethod
    def _event(connection: sqlite3.Connection, execution_id: str, event_type: str) -> None:
        connection.execute(
            "INSERT INTO integration_checkpoint_events (event_id, execution_id, occurred_at, event_type) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), execution_id, _utc_now(), event_type),
        )

    def get(self, execution_id: str) -> IntegrationCheckpoint | None:
        execution_id = _identifier(execution_id, "execution_id")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM integration_checkpoints WHERE execution_id = ?", (execution_id,)).fetchone()
        return self._from_row(row) if row is not None else None

    def prepare(self, execution_id: str, request_id: str) -> IntegrationCheckpoint:
        execution_id = _identifier(execution_id, "execution_id")
        request_id = _identifier(request_id, "request_id")
        plan_json = json.dumps(_PLAN, sort_keys=True, separators=(",", ":"))
        plan_digest = hashlib.sha256(plan_json.encode("utf-8")).hexdigest()
        now = _utc_now()
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM integration_checkpoints WHERE execution_id = ?", (execution_id,)).fetchone()
            if row is not None:
                existing = self._from_row(row)
                raise IntegrationCheckpointError(
                    f"Execution already has checkpoint state {existing.state}; automatic replay is refused."
                )
            connection.execute(
                """
                INSERT INTO integration_checkpoints (
                    execution_id, request_id, state, plan_digest, created_at, updated_at
                ) VALUES (?, ?, 'prepared', ?, ?, ?)
                """,
                (execution_id, request_id, plan_digest, now, now),
            )
            self._event(connection, execution_id, "checkpoint_prepared")
        return IntegrationCheckpoint(execution_id, request_id, "prepared", plan_digest, now, now, None, None, None, None, None)

    def begin_agent_step(self, execution_id: str) -> IntegrationCheckpoint:
        execution_id = _identifier(execution_id, "execution_id")
        now = _utc_now()
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM integration_checkpoints WHERE execution_id = ?", (execution_id,)).fetchone()
            if row is None:
                raise IntegrationCheckpointError("Execution checkpoint was not found.")
            current = self._from_row(row)
            if current.state != "prepared":
                raise IntegrationCheckpointError("Only a prepared checkpoint may start the agent step.")
            connection.execute(
                "UPDATE integration_checkpoints SET state = 'in_progress', step_started_at = ?, updated_at = ? WHERE execution_id = ?",
                (now, now, execution_id),
            )
            self._event(connection, execution_id, "checkpoint_agent_step_started")
        return IntegrationCheckpoint(current.execution_id, current.request_id, "in_progress", current.plan_digest, current.created_at, now, now, None, None, None, None)

    def finish(self, execution_id: str, result_status: str, result_text: str) -> IntegrationCheckpoint:
        execution_id = _identifier(execution_id, "execution_id")
        result_status = _identifier(result_status, "result_status")
        if not isinstance(result_text, str):
            raise IntegrationCheckpointError("result_text must be a string.")
        now = _utc_now()
        digest = hashlib.sha256(result_text.encode("utf-8")).hexdigest()
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM integration_checkpoints WHERE execution_id = ?", (execution_id,)).fetchone()
            if row is None:
                raise IntegrationCheckpointError("Execution checkpoint was not found.")
            current = self._from_row(row)
            if current.state != "in_progress":
                raise IntegrationCheckpointError("Only an in-progress checkpoint may receive a result receipt.")
            connection.execute(
                """
                UPDATE integration_checkpoints
                SET state = 'completed', updated_at = ?, completed_at = ?, result_status = ?, result_digest = ?
                WHERE execution_id = ?
                """,
                (now, now, result_status, digest, execution_id),
            )
            self._event(connection, execution_id, "checkpoint_completed")
        return IntegrationCheckpoint(current.execution_id, current.request_id, "completed", current.plan_digest, current.created_at, now, current.step_started_at, now, result_status, digest, None)

    def mark_uncertain(self, execution_id: str, reason: str) -> IntegrationCheckpoint | None:
        execution_id = _identifier(execution_id, "execution_id")
        reason = _identifier(reason, "recovery_reason")
        now = _utc_now()
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM integration_checkpoints WHERE execution_id = ?", (execution_id,)).fetchone()
            if row is None:
                return None
            current = self._from_row(row)
            if current.state in {"completed", "uncertain"}:
                return current
            connection.execute(
                "UPDATE integration_checkpoints SET state = 'uncertain', updated_at = ?, recovery_reason = ? WHERE execution_id = ?",
                (now, reason, execution_id),
            )
            self._event(connection, execution_id, "checkpoint_marked_uncertain")
        return IntegrationCheckpoint(current.execution_id, current.request_id, "uncertain", current.plan_digest, current.created_at, now, current.step_started_at, current.completed_at, current.result_status, current.result_digest, reason)
