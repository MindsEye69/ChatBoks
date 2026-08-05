"""Durable state for future isolated integration execution runners.

This registry deliberately does not attach to ChatBoks' current project-wide
stop path. A runner must register an isolated execution before any lifecycle
mutation can safely target it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import uuid


_SCHEMA_VERSION = 3
_MAX_IDENTIFIER_CHARS = 128
_MAX_METADATA_CHARS = 128
_MAX_EVENT_PAGE_SIZE = 128
_INITIAL_STATUS = "waiting_for_runner"
_TERMINAL_STATUSES = {"cancelled", "succeeded", "failed", "blocked", "interrupted"}
_STATUSES = {
    _INITIAL_STATUS,
    "running",
    "paused",
    "cancellation_requested",
    *_TERMINAL_STATUSES,
}


class IntegrationExecutionError(ValueError):
    """An execution record cannot make the requested safe state transition."""


@dataclass(frozen=True)
class IntegrationExecution:
    execution_id: str
    request_id: str
    status: str
    session_id: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    error_code: str | None
    runner_pid: int | None
    last_heartbeat_at: str | None
    active_role: str | None
    current_operation: str | None
    expected_next_transition: str | None


@dataclass(frozen=True)
class IntegrationExecutionEvent:
    sequence: int
    event_id: str
    execution_id: str
    occurred_at: str
    event_type: str


def default_execution_registry_path(project_path: Path) -> Path:
    return project_path / ".chatboks" / "integration-executions.sqlite3"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise IntegrationExecutionError(f"{label} must be a bounded string.")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_IDENTIFIER_CHARS:
        raise IntegrationExecutionError(f"{label} must be a bounded string.")
    return cleaned


def _optional_metadata(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise IntegrationExecutionError(f"{label} must be a bounded string.")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_METADATA_CHARS:
        raise IntegrationExecutionError(f"{label} must be a bounded string.")
    return cleaned


class IntegrationExecutionRegistry:
    """Project-local execution identity and event source for isolated runners."""

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
    def _connection_scope(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
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
        with self._connection_scope() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > _SCHEMA_VERSION:
                raise IntegrationExecutionError(
                    f"Execution registry schema {version} is newer than this ChatBoks version supports."
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS integration_executions (
                    execution_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status IN (
                        'waiting_for_runner', 'running', 'paused', 'cancellation_requested',
                        'cancelled', 'succeeded', 'failed', 'blocked', 'interrupted'
                    )),
                    session_id TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_code TEXT,
                    runner_pid INTEGER,
                    last_heartbeat_at TEXT,
                    active_role TEXT,
                    current_operation TEXT,
                    expected_next_transition TEXT
                );
                CREATE TABLE IF NOT EXISTS integration_execution_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    execution_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    FOREIGN KEY(execution_id) REFERENCES integration_executions(execution_id)
                );
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(integration_executions)").fetchall()
            }
            if "runner_pid" not in columns:
                connection.execute("ALTER TABLE integration_executions ADD COLUMN runner_pid INTEGER")
            if "last_heartbeat_at" not in columns:
                connection.execute("ALTER TABLE integration_executions ADD COLUMN last_heartbeat_at TEXT")
            if "active_role" not in columns:
                connection.execute("ALTER TABLE integration_executions ADD COLUMN active_role TEXT")
            if "current_operation" not in columns:
                connection.execute("ALTER TABLE integration_executions ADD COLUMN current_operation TEXT")
            if "expected_next_transition" not in columns:
                connection.execute(
                    "ALTER TABLE integration_executions ADD COLUMN expected_next_transition TEXT"
                )
            if version < _SCHEMA_VERSION:
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> IntegrationExecution:
        return IntegrationExecution(
            execution_id=str(row["execution_id"]),
            request_id=str(row["request_id"]),
            status=str(row["status"]),
            session_id=str(row["session_id"]) if row["session_id"] is not None else None,
            created_at=str(row["created_at"]),
            started_at=str(row["started_at"]) if row["started_at"] is not None else None,
            completed_at=str(row["completed_at"]) if row["completed_at"] is not None else None,
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
            runner_pid=int(row["runner_pid"]) if row["runner_pid"] is not None else None,
            last_heartbeat_at=(
                str(row["last_heartbeat_at"]) if row["last_heartbeat_at"] is not None else None
            ),
            active_role=str(row["active_role"]) if row["active_role"] is not None else None,
            current_operation=(
                str(row["current_operation"]) if row["current_operation"] is not None else None
            ),
            expected_next_transition=(
                str(row["expected_next_transition"])
                if row["expected_next_transition"] is not None
                else None
            ),
        )

    @staticmethod
    def _append_event(connection: sqlite3.Connection, execution_id: str, event_type: str) -> None:
        connection.execute(
            """
            INSERT INTO integration_execution_events (event_id, execution_id, occurred_at, event_type)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), execution_id, _utc_now(), event_type),
        )

    @staticmethod
    def _current(connection: sqlite3.Connection, execution_id: str) -> IntegrationExecution:
        row = connection.execute(
            "SELECT * FROM integration_executions WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        if row is None:
            raise IntegrationExecutionError("Integration execution was not found.")
        return IntegrationExecutionRegistry._from_row(row)

    def reserve(self, request_id: str) -> IntegrationExecution:
        """Idempotently reserve one execution identity for an approved request."""
        request_id = _require_identifier(request_id, "request_id")
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM integration_executions WHERE request_id = ?", (request_id,)
            ).fetchone()
            if row is not None:
                return self._from_row(row)
            execution_id = f"execution-{uuid.uuid4()}"
            created_at = _utc_now()
            connection.execute(
                """
                INSERT INTO integration_executions (execution_id, request_id, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (execution_id, request_id, _INITIAL_STATUS, created_at),
            )
            self._append_event(connection, execution_id, "execution_reserved")
        return IntegrationExecution(
            execution_id, request_id, _INITIAL_STATUS, None, created_at, None, None, None, None,
            None, None, None, None,
        )

    def get(self, execution_id: str) -> IntegrationExecution | None:
        execution_id = _require_identifier(execution_id, "execution_id")
        with self._connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM integration_executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def get_for_request(self, request_id: str) -> IntegrationExecution | None:
        request_id = _require_identifier(request_id, "request_id")
        with self._connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM integration_executions WHERE request_id = ?", (request_id,)
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def start(self, execution_id: str, session_id: str) -> IntegrationExecution:
        execution_id = _require_identifier(execution_id, "execution_id")
        session_id = _require_identifier(session_id, "session_id")
        started_at = _utc_now()
        with self._write_transaction() as connection:
            current = self._current(connection, execution_id)
            if current.status != _INITIAL_STATUS:
                raise IntegrationExecutionError("Only a reserved execution may be started.")
            connection.execute(
                """
                UPDATE integration_executions
                SET status = 'running', session_id = ?, started_at = ?, last_heartbeat_at = ?,
                    current_operation = 'preparing_execution', expected_next_transition = 'agent_load'
                WHERE execution_id = ?
                """,
                (session_id, started_at, started_at, execution_id),
            )
            self._append_event(connection, execution_id, "execution_started")
        return IntegrationExecution(
            execution_id,
            current.request_id,
            "running",
            session_id,
            current.created_at,
            started_at,
            None,
            None,
            current.runner_pid,
            started_at,
            None,
            "preparing_execution",
            "agent_load",
        )

    def attach_runner(self, execution_id: str, runner_pid: int) -> IntegrationExecution:
        """Attach one process-owned runner while an isolated task is being claimed."""
        execution_id = _require_identifier(execution_id, "execution_id")
        if isinstance(runner_pid, bool) or not isinstance(runner_pid, int) or runner_pid <= 0:
            raise IntegrationExecutionError("Runner pid must be a positive integer.")
        with self._write_transaction() as connection:
            current = self._current(connection, execution_id)
            if current.status not in {_INITIAL_STATUS, "running"}:
                raise IntegrationExecutionError("Only an active or reserved execution may attach a runner.")
            if current.runner_pid is not None and current.runner_pid != runner_pid:
                raise IntegrationExecutionError("Execution already has a different runner.")
            if current.runner_pid == runner_pid:
                return current
            connection.execute(
                "UPDATE integration_executions SET runner_pid = ? WHERE execution_id = ?",
                (runner_pid, execution_id),
            )
            self._append_event(connection, execution_id, "runner_attached")
        return IntegrationExecution(
            current.execution_id,
            current.request_id,
            current.status,
            current.session_id,
            current.created_at,
            current.started_at,
            current.completed_at,
            current.error_code,
            runner_pid,
            current.last_heartbeat_at,
            current.active_role,
            current.current_operation,
            current.expected_next_transition,
        )

    def set_activity(
        self,
        execution_id: str,
        *,
        active_role: str,
        current_operation: str,
        expected_next_transition: str,
    ) -> IntegrationExecution:
        """Publish bounded worker metadata after an actual lifecycle boundary."""
        execution_id = _require_identifier(execution_id, "execution_id")
        active_role = _optional_metadata(active_role, "active_role")
        current_operation = _optional_metadata(current_operation, "current_operation")
        expected_next_transition = _optional_metadata(
            expected_next_transition, "expected_next_transition"
        )
        assert active_role is not None
        assert current_operation is not None
        assert expected_next_transition is not None
        heartbeat_at = _utc_now()
        with self._write_transaction() as connection:
            current = self._current(connection, execution_id)
            if current.status != "running":
                raise IntegrationExecutionError("Only a running execution may publish activity.")
            connection.execute(
                """
                UPDATE integration_executions
                SET active_role = ?, current_operation = ?, expected_next_transition = ?,
                    last_heartbeat_at = ?
                WHERE execution_id = ?
                """,
                (active_role, current_operation, expected_next_transition, heartbeat_at, execution_id),
            )
            self._append_event(connection, execution_id, "execution_activity_updated")
        return IntegrationExecution(
            current.execution_id, current.request_id, current.status, current.session_id,
            current.created_at, current.started_at, current.completed_at, current.error_code,
            current.runner_pid, heartbeat_at, active_role, current_operation, expected_next_transition,
        )

    def heartbeat(self, execution_id: str) -> IntegrationExecution:
        """Record that the owned worker is still alive without exposing task material."""
        execution_id = _require_identifier(execution_id, "execution_id")
        heartbeat_at = _utc_now()
        with self._write_transaction() as connection:
            current = self._current(connection, execution_id)
            if current.status != "running":
                raise IntegrationExecutionError("Only a running execution may emit a heartbeat.")
            connection.execute(
                "UPDATE integration_executions SET last_heartbeat_at = ? WHERE execution_id = ?",
                (heartbeat_at, execution_id),
            )
            self._append_event(connection, execution_id, "execution_heartbeat")
        return IntegrationExecution(
            current.execution_id, current.request_id, current.status, current.session_id,
            current.created_at, current.started_at, current.completed_at, current.error_code,
            current.runner_pid, heartbeat_at, current.active_role, current.current_operation,
            current.expected_next_transition,
        )

    def mark_runner_failed_to_start(self, execution_id: str, error_code: str) -> IntegrationExecution:
        """Record a launch failure without pretending that a task ever started."""
        error_code = _require_identifier(error_code, "error_code")
        execution_id = _require_identifier(execution_id, "execution_id")
        with self._write_transaction() as connection:
            current = self._current(connection, execution_id)
            if current.status != _INITIAL_STATUS:
                raise IntegrationExecutionError("Only a reserved execution may fail to start.")
            return self._transition_in_transaction(
                connection,
                current,
                status="failed",
                event_type="runner_failed_to_start",
                completed_at=_utc_now(),
                error_code=error_code,
            )

    def pause(self, execution_id: str) -> IntegrationExecution:
        return self._transition(
            execution_id,
            allowed={"running"},
            status="paused",
            event_type="execution_paused",
        )

    def resume(self, execution_id: str) -> IntegrationExecution:
        return self._transition(
            execution_id,
            allowed={"paused"},
            status="running",
            event_type="execution_resumed",
        )

    def request_cancellation(self, execution_id: str) -> IntegrationExecution:
        execution_id = _require_identifier(execution_id, "execution_id")
        with self._write_transaction() as connection:
            current = self._current(connection, execution_id)
            if current.status == _INITIAL_STATUS:
                return self._transition_in_transaction(
                    connection,
                    current,
                    status="cancelled",
                    event_type="execution_cancelled_before_start",
                    completed_at=_utc_now(),
                )
            if current.status == "cancellation_requested":
                return current
            if current.status not in {"running", "paused"}:
                raise IntegrationExecutionError("Only an active execution may receive a cancellation request.")
            return self._transition_in_transaction(
                connection,
                current,
                status="cancellation_requested",
                event_type="execution_cancellation_requested",
            )

    def finish(self, execution_id: str, status: str, error_code: str = "") -> IntegrationExecution:
        execution_id = _require_identifier(execution_id, "execution_id")
        if status not in {"cancelled", "succeeded", "failed", "blocked"}:
            raise IntegrationExecutionError("Execution completion status is not supported.")
        if not isinstance(error_code, str):
            raise IntegrationExecutionError("error_code must be a bounded string.")
        error_code = error_code.strip()
        if len(error_code) > _MAX_IDENTIFIER_CHARS:
            raise IntegrationExecutionError("error_code must be a bounded string.")
        with self._write_transaction() as connection:
            current = self._current(connection, execution_id)
            allowed = {"cancellation_requested"} if status == "cancelled" else {"running"}
            if current.status not in allowed:
                raise IntegrationExecutionError("Execution cannot complete from its current state.")
            return self._transition_in_transaction(
                connection,
                current,
                status=status,
                event_type=f"execution_{status}",
                completed_at=_utc_now(),
                error_code=error_code or None,
            )

    def mark_interrupted(self, execution_id: str) -> IntegrationExecution:
        return self._transition(
            execution_id,
            allowed={"running", "cancellation_requested"},
            status="interrupted",
            event_type="execution_interrupted",
            completed_at=_utc_now(),
        )

    def _transition(
        self,
        execution_id: str,
        *,
        allowed: set[str],
        status: str,
        event_type: str,
        completed_at: str | None = None,
    ) -> IntegrationExecution:
        execution_id = _require_identifier(execution_id, "execution_id")
        with self._write_transaction() as connection:
            current = self._current(connection, execution_id)
            if current.status not in allowed:
                raise IntegrationExecutionError("Execution cannot make that state transition.")
            return self._transition_in_transaction(
                connection, current, status=status, event_type=event_type, completed_at=completed_at
            )

    def _transition_in_transaction(
        self,
        connection: sqlite3.Connection,
        current: IntegrationExecution,
        *,
        status: str,
        event_type: str,
        completed_at: str | None = None,
        error_code: str | None = None,
    ) -> IntegrationExecution:
        if status not in _STATUSES:
            raise IntegrationExecutionError("Execution status is not supported.")
        connection.execute(
            """
            UPDATE integration_executions
            SET status = ?, completed_at = ?, error_code = ?, current_operation = ?,
                expected_next_transition = ?
            WHERE execution_id = ?
            """,
            (
                status,
                completed_at if completed_at is not None else current.completed_at,
                error_code if error_code is not None else current.error_code,
                status if status in _TERMINAL_STATUSES else current.current_operation,
                None if status in _TERMINAL_STATUSES else current.expected_next_transition,
                current.execution_id,
            ),
        )
        self._append_event(connection, current.execution_id, event_type)
        return IntegrationExecution(
            current.execution_id,
            current.request_id,
            status,
            current.session_id,
            current.created_at,
            current.started_at,
            completed_at if completed_at is not None else current.completed_at,
            error_code if error_code is not None else current.error_code,
            current.runner_pid,
            current.last_heartbeat_at,
            current.active_role,
            status if status in _TERMINAL_STATUSES else current.current_operation,
            None if status in _TERMINAL_STATUSES else current.expected_next_transition,
        )

    def events(
        self, execution_id: str, *, after_sequence: int = 0, limit: int = _MAX_EVENT_PAGE_SIZE
    ) -> list[IntegrationExecutionEvent]:
        execution_id = _require_identifier(execution_id, "execution_id")
        if isinstance(after_sequence, bool) or not isinstance(after_sequence, int) or after_sequence < 0:
            raise IntegrationExecutionError("Event cursor must be a non-negative integer.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_EVENT_PAGE_SIZE:
            raise IntegrationExecutionError(f"Event page size must be between 1 and {_MAX_EVENT_PAGE_SIZE}.")
        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT sequence, event_id, execution_id, occurred_at, event_type
                FROM integration_execution_events
                WHERE execution_id = ? AND sequence > ?
                ORDER BY sequence ASC
                LIMIT ?
                """,
                (execution_id, after_sequence, limit),
            ).fetchall()
        return [
            IntegrationExecutionEvent(
                sequence=int(row["sequence"]),
                event_id=str(row["event_id"]),
                execution_id=str(row["execution_id"]),
                occurred_at=str(row["occurred_at"]),
                event_type=str(row["event_type"]),
            )
            for row in rows
        ]
