"""Durable, local approval queue for verified integration requests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from integration_capabilities import (
    IntegrationCapabilityError,
    get_integration_capability,
    validate_capability_scope,
)
from integration_proofs import PairedProofDecision
from ticket_execution import TicketExecutionValidationError, parse_ticket_execution


_QUEUE_SCHEMA_VERSION = 5
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_NOTE_BYTES = 1_000
_MAX_EVENT_PAGE_SIZE = 128
_APPROVAL_TTL = timedelta(minutes=15)
_STATUSES = {"pending", "approved", "rejected", "dispatched"}


class IntegrationRequestError(ValueError):
    """A request cannot enter or transition through the local approval queue."""


@dataclass(frozen=True)
class QueuedIntegrationRequest:
    request_id: str
    ticket_id: str
    capability_id: str
    correlation_id: str
    request: dict[str, Any]
    idempotency_key: str | None
    idempotency_digest: str | None
    client_id: str
    key_id: str
    proof_id: str
    received_at: str
    status: str
    decided_at: str | None
    decision_note: str | None
    dispatched_at: str | None
    execution_session_id: str | None
    approved_capability_id: str | None = None
    approval_receipt_id: str | None = None
    approval_expires_at: str | None = None
    approval_revoked_at: str | None = None
    revocation_note: str | None = None


@dataclass(frozen=True)
class IntegrationRequestEvent:
    sequence: int
    event_id: str
    request_id: str
    occurred_at: str
    event_type: str


def default_request_queue_path(project_path: Path) -> Path:
    return project_path / ".chatboks" / "integration-requests.sqlite3"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _utc_after(duration: timedelta) -> str:
    return (datetime.now(UTC) + duration).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _approval_is_expired(value: str | None) -> bool:
    if value is None:
        return True
    try:
        expires_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    return expires_at <= datetime.now(UTC)


def _canonical_request(request: Mapping[str, Any]) -> str:
    if not isinstance(request, Mapping):
        raise IntegrationRequestError("Verified request must be a JSON object.")
    try:
        encoded = json.dumps(
            dict(request), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise IntegrationRequestError("Verified request cannot be encoded as JSON.") from exc
    if len(encoded.encode("utf-8")) > _MAX_REQUEST_BYTES:
        raise IntegrationRequestError(f"Verified request exceeds the {_MAX_REQUEST_BYTES}-byte limit.")
    return encoded


def _require_string(request: Mapping[str, Any], name: str, maximum: int = 128) -> str:
    value = request.get(name)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise IntegrationRequestError(f"Verified request requires a bounded {name} string.")
    return value


class IntegrationRequestQueue:
    """Project-local queue whose only initial transition is explicit approval."""

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
        """Commit completed work and always release the SQLite file handle."""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection_scope() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > _QUEUE_SCHEMA_VERSION:
                raise IntegrationRequestError(
                    f"Request queue schema {version} is newer than this ChatBoks version supports."
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS integration_requests (
                    request_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, capability_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL, request_json TEXT NOT NULL, request_digest TEXT NOT NULL,
                    idempotency_key TEXT, idempotency_digest TEXT,
                    client_id TEXT NOT NULL, key_id TEXT NOT NULL, proof_id TEXT NOT NULL UNIQUE,
                    received_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'dispatched')),
                    decided_at TEXT, decision_note TEXT, dispatched_at TEXT,
                    execution_session_id TEXT, approved_capability_id TEXT,
                    approval_receipt_id TEXT UNIQUE, approval_expires_at TEXT,
                    approval_revoked_at TEXT, revocation_note TEXT
                );
                CREATE TABLE IF NOT EXISTS integration_request_events (
                    event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    event_type TEXT NOT NULL, detail_json TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES integration_requests(request_id)
                );
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(integration_requests)").fetchall()
            }
            if "execution_session_id" not in columns:
                connection.execute(
                    "ALTER TABLE integration_requests ADD COLUMN execution_session_id TEXT"
                )
            if "idempotency_key" not in columns:
                connection.execute(
                    "ALTER TABLE integration_requests ADD COLUMN idempotency_key TEXT"
                )
            if "idempotency_digest" not in columns:
                connection.execute(
                    "ALTER TABLE integration_requests ADD COLUMN idempotency_digest TEXT"
                )
            if "approved_capability_id" not in columns:
                connection.execute(
                    "ALTER TABLE integration_requests ADD COLUMN approved_capability_id TEXT"
                )
            if "approval_receipt_id" not in columns:
                connection.execute(
                    "ALTER TABLE integration_requests ADD COLUMN approval_receipt_id TEXT"
                )
            if "approval_expires_at" not in columns:
                connection.execute(
                    "ALTER TABLE integration_requests ADD COLUMN approval_expires_at TEXT"
                )
            if "approval_revoked_at" not in columns:
                connection.execute(
                    "ALTER TABLE integration_requests ADD COLUMN approval_revoked_at TEXT"
                )
            if "revocation_note" not in columns:
                connection.execute(
                    "ALTER TABLE integration_requests ADD COLUMN revocation_note TEXT"
                )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS integration_requests_idempotency_key
                ON integration_requests(client_id, ticket_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS integration_requests_approval_receipt
                ON integration_requests(approval_receipt_id)
                WHERE approval_receipt_id IS NOT NULL
                """
            )
            if version < _QUEUE_SCHEMA_VERSION:
                connection.execute(f"PRAGMA user_version = {_QUEUE_SCHEMA_VERSION}")

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

    @staticmethod
    def _from_row(row: sqlite3.Row) -> QueuedIntegrationRequest:
        return QueuedIntegrationRequest(
            request_id=str(row["request_id"]),
            ticket_id=str(row["ticket_id"]),
            capability_id=str(row["capability_id"]),
            correlation_id=str(row["correlation_id"]),
            request=json.loads(str(row["request_json"])),
            idempotency_key=str(row["idempotency_key"]) if row["idempotency_key"] is not None else None,
            idempotency_digest=(
                str(row["idempotency_digest"])
                if row["idempotency_digest"] is not None
                else None
            ),
            client_id=str(row["client_id"]),
            key_id=str(row["key_id"]),
            proof_id=str(row["proof_id"]),
            received_at=str(row["received_at"]),
            status=str(row["status"]),
            decided_at=str(row["decided_at"]) if row["decided_at"] is not None else None,
            decision_note=str(row["decision_note"]) if row["decision_note"] is not None else None,
            dispatched_at=str(row["dispatched_at"]) if row["dispatched_at"] is not None else None,
            execution_session_id=(
                str(row["execution_session_id"])
                if row["execution_session_id"] is not None
                else None
            ),
            approved_capability_id=(
                str(row["approved_capability_id"])
                if row["approved_capability_id"] is not None
                else None
            ),
            approval_receipt_id=(
                str(row["approval_receipt_id"])
                if row["approval_receipt_id"] is not None
                else None
            ),
            approval_expires_at=(
                str(row["approval_expires_at"])
                if row["approval_expires_at"] is not None
                else None
            ),
            approval_revoked_at=(
                str(row["approval_revoked_at"])
                if row["approval_revoked_at"] is not None
                else None
            ),
            revocation_note=(
                str(row["revocation_note"])
                if row["revocation_note"] is not None
                else None
            ),
        )

    def submit_verified(self, decision: PairedProofDecision) -> QueuedIntegrationRequest:
        """Store provenance-verified work as pending; this never starts a task."""
        request_json = _canonical_request(decision.request)
        request = json.loads(request_json)
        request_id = _require_string(request, "requestId")
        ticket_id = _require_string(request, "ticketId", 64)
        capability_id = _require_string(request, "capabilityId")
        correlation_id = _require_string(request, "correlationId")
        if request.get("targetApplicationId") != "chatboks":
            raise IntegrationRequestError("Verified request is not addressed to ChatBoks.")
        try:
            ticket_execution = parse_ticket_execution(request)
        except TicketExecutionValidationError as exc:
            raise IntegrationRequestError(str(exc)) from exc
        try:
            validate_capability_scope(capability_id, ticket_execution)
        except IntegrationCapabilityError as exc:
            raise IntegrationRequestError(str(exc)) from exc
        digest = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        idempotency_key = ticket_execution.idempotency_key if ticket_execution is not None else None
        idempotency_digest = (
            ticket_execution.idempotency_digest(ticket_id=ticket_id, capability_id=capability_id)
            if ticket_execution is not None
            else None
        )
        received_at = _utc_now()
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM integration_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
            if row is not None:
                existing = self._from_row(row)
                existing_json = _canonical_request(existing.request)
                if (
                    existing.proof_id == decision.proof_id
                    and existing.client_id == decision.client_id
                    and existing.key_id == decision.key_id
                    and hashlib.sha256(existing_json.encode("utf-8")).hexdigest() == digest
                ):
                    return existing
                raise IntegrationRequestError("A different request or proof already uses this request_id.")
            proof_row = connection.execute(
                "SELECT * FROM integration_requests WHERE proof_id = ?", (decision.proof_id,)
            ).fetchone()
            if proof_row is not None:
                raise IntegrationRequestError("A request proof cannot be reused with a different request_id.")
            if idempotency_key is not None:
                idempotent_row = connection.execute(
                    """
                    SELECT * FROM integration_requests
                    WHERE client_id = ? AND ticket_id = ? AND idempotency_key = ?
                    """,
                    (decision.client_id, ticket_id, idempotency_key),
                ).fetchone()
                if idempotent_row is not None:
                    existing = self._from_row(idempotent_row)
                    if existing.idempotency_digest == idempotency_digest:
                        return existing
                    raise IntegrationRequestError(
                        "A different ticket payload already uses this idempotencyKey."
                    )
            connection.execute(
                """
                INSERT INTO integration_requests (
                    request_id, ticket_id, capability_id, correlation_id, request_json, request_digest,
                    idempotency_key, idempotency_digest, client_id, key_id, proof_id, received_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    request_id,
                    ticket_id,
                    capability_id,
                    correlation_id,
                    request_json,
                    digest,
                    idempotency_key,
                    idempotency_digest,
                    decision.client_id,
                    decision.key_id,
                    decision.proof_id,
                    received_at,
                ),
            )
            self._append_event(
                connection, request_id, "request_received",
                {"client_id": decision.client_id, "key_id": decision.key_id,
                 "proof_id": decision.proof_id, "request_digest": digest},
            )
        return QueuedIntegrationRequest(
            request_id=request_id,
            ticket_id=ticket_id,
            capability_id=capability_id,
            correlation_id=correlation_id,
            request=request,
            idempotency_key=idempotency_key,
            idempotency_digest=idempotency_digest,
            client_id=decision.client_id,
            key_id=decision.key_id,
            proof_id=decision.proof_id,
            received_at=received_at,
            status="pending",
            decided_at=None,
            decision_note=None,
            dispatched_at=None,
            execution_session_id=None,
        )

    def get(self, request_id: str) -> QueuedIntegrationRequest | None:
        with self._connection_scope() as connection:
            row = connection.execute("SELECT * FROM integration_requests WHERE request_id = ?", (request_id,)).fetchone()
        return self._from_row(row) if row is not None else None

    def list(self, *, status: str | None = None) -> list[QueuedIntegrationRequest]:
        if status is not None and status not in _STATUSES:
            raise IntegrationRequestError("Unknown integration request status.")
        query, params = "SELECT * FROM integration_requests", ()
        if status is not None:
            query, params = f"{query} WHERE status = ?", (status,)
        with self._connection_scope() as connection:
            rows = connection.execute(f"{query} ORDER BY received_at DESC", params).fetchall()
        return [self._from_row(row) for row in rows]

    def events(
        self, request_id: str, *, after_sequence: int = 0, limit: int = _MAX_EVENT_PAGE_SIZE
    ) -> list[IntegrationRequestEvent]:
        """Return metadata-only, cursor-addressable lifecycle events for one request."""
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            raise IntegrationRequestError("Integration request id must be a bounded string.")
        if isinstance(after_sequence, bool) or not isinstance(after_sequence, int) or after_sequence < 0:
            raise IntegrationRequestError("Event cursor must be a non-negative integer.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_EVENT_PAGE_SIZE:
            raise IntegrationRequestError(f"Event page size must be between 1 and {_MAX_EVENT_PAGE_SIZE}.")
        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT rowid AS sequence, event_id, request_id, occurred_at, event_type
                FROM integration_request_events
                WHERE request_id = ? AND rowid > ?
                ORDER BY rowid ASC
                LIMIT ?
                """,
                (request_id, after_sequence, limit),
            ).fetchall()
        return [
            IntegrationRequestEvent(
                sequence=int(row["sequence"]),
                event_id=str(row["event_id"]),
                request_id=str(row["request_id"]),
                occurred_at=str(row["occurred_at"]),
                event_type=str(row["event_type"]),
            )
            for row in rows
        ]

    def approve(self, request_id: str, note: str = "") -> QueuedIntegrationRequest:
        return self._decide(request_id, "approved", note)

    def reject(self, request_id: str, note: str = "") -> QueuedIntegrationRequest:
        return self._decide(request_id, "rejected", note)

    def revoke_approval(self, request_id: str, note: str = "") -> QueuedIntegrationRequest:
        """Revoke an undispatched approval; running work must be cancelled separately."""
        note = note.strip()
        if len(note.encode("utf-8")) > _MAX_NOTE_BYTES:
            raise IntegrationRequestError("Revocation note exceeds the 1000-byte limit.")
        revoked_at = _utc_now()
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM integration_requests WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise IntegrationRequestError("Integration request was not found.")
            current = self._from_row(row)
            if current.status != "approved":
                raise IntegrationRequestError("Only an approved, undispatched integration request may be revoked.")
            connection.execute(
                """
                UPDATE integration_requests
                SET status = 'rejected', approval_revoked_at = ?, revocation_note = ?
                WHERE request_id = ?
                """,
                (revoked_at, note or None, request_id),
            )
            self._append_event(
                connection,
                request_id,
                "approval_revoked",
                {"note": note, "capability_id": current.approved_capability_id},
            )
        return replace(
            current,
            status="rejected",
            approval_revoked_at=revoked_at,
            revocation_note=note or None,
        )

    def _decide(self, request_id: str, outcome: str, note: str) -> QueuedIntegrationRequest:
        note = note.strip()
        if len(note.encode("utf-8")) > _MAX_NOTE_BYTES:
            raise IntegrationRequestError("Decision note exceeds the 1000-byte limit.")
        decided_at = _utc_now()
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM integration_requests WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise IntegrationRequestError("Integration request was not found.")
            current = self._from_row(row)
            if current.status != "pending":
                raise IntegrationRequestError(f"Integration request is already {current.status} and cannot be {outcome}.")
            approved_capability_id = None
            approval_receipt_id = None
            approval_expires_at = None
            if outcome == "approved":
                try:
                    capability = get_integration_capability(current.capability_id)
                except IntegrationCapabilityError as exc:
                    raise IntegrationRequestError(str(exc)) from exc
                if capability.requires_local_approval:
                    approved_capability_id = capability.capability_id
                    approval_receipt_id = str(uuid.uuid4())
                    approval_expires_at = _utc_after(_APPROVAL_TTL)
            connection.execute(
                """
                UPDATE integration_requests
                SET status = ?, decided_at = ?, decision_note = ?, approved_capability_id = ?,
                    approval_receipt_id = ?, approval_expires_at = ?, approval_revoked_at = NULL,
                    revocation_note = NULL
                WHERE request_id = ?
                """,
                (
                    outcome,
                    decided_at,
                    note or None,
                    approved_capability_id,
                    approval_receipt_id,
                    approval_expires_at,
                    request_id,
                ),
            )
            detail: dict[str, Any] = {"note": note}
            if approved_capability_id is not None and approval_receipt_id is not None:
                detail.update(
                    {
                        "capability_id": approved_capability_id,
                        "approval_receipt_id": approval_receipt_id,
                        "approval_expires_at": approval_expires_at,
                    }
                )
            self._append_event(connection, request_id, f"request_{outcome}", detail)
        return replace(
            current,
            status=outcome,
            decided_at=decided_at,
            decision_note=note or None,
            approved_capability_id=approved_capability_id,
            approval_receipt_id=approval_receipt_id,
            approval_expires_at=approval_expires_at,
            approval_revoked_at=None,
            revocation_note=None,
        )

    def mark_dispatched(
        self, request_id: str, execution_session_id: str
    ) -> QueuedIntegrationRequest:
        """Link approved work to its local ChatBoks session before routing it."""
        if not isinstance(execution_session_id, str):
            raise IntegrationRequestError("Dispatch requires a bounded ChatBoks session identifier.")
        execution_session_id = execution_session_id.strip()
        if not execution_session_id or len(execution_session_id) > 128:
            raise IntegrationRequestError("Dispatch requires a bounded ChatBoks session identifier.")
        dispatched_at = _utc_now()
        expired = False
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM integration_requests WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise IntegrationRequestError("Integration request was not found.")
            current = self._from_row(row)
            if current.status != "approved":
                raise IntegrationRequestError("Only an explicitly approved integration request may be dispatched.")
            if _approval_is_expired(current.approval_expires_at):
                connection.execute(
                    "UPDATE integration_requests SET status = 'rejected' WHERE request_id = ?",
                    (request_id,),
                )
                self._append_event(
                    connection,
                    request_id,
                    "approval_expired",
                    {"approval_receipt_id": current.approval_receipt_id},
                )
                expired = True
            if not expired:
                try:
                    ticket_execution = parse_ticket_execution(current.request)
                    capability = validate_capability_scope(current.capability_id, ticket_execution)
                except (TicketExecutionValidationError, IntegrationCapabilityError) as exc:
                    raise IntegrationRequestError(str(exc)) from exc
                if capability.requires_local_approval and (
                    current.approved_capability_id != capability.capability_id
                    or current.approval_receipt_id is None
                ):
                    raise IntegrationRequestError(
                        "Dispatch requires an active local approval receipt for the requested capability."
                    )
                connection.execute(
                    """
                    UPDATE integration_requests
                    SET status = 'dispatched', dispatched_at = ?, execution_session_id = ?
                    WHERE request_id = ?
                    """,
                    (dispatched_at, execution_session_id, request_id),
                )
                self._append_event(
                    connection, request_id, "request_dispatched", {"session_id": execution_session_id}
                )
        if expired:
            raise IntegrationRequestError("The local approval receipt expired before dispatch.")
        return replace(
            current,
            status="dispatched",
            dispatched_at=dispatched_at,
            execution_session_id=execution_session_id,
        )

    @staticmethod
    def _append_event(connection: sqlite3.Connection, request_id: str, event_type: str, detail: Mapping[str, Any]) -> None:
        detail_json = json.dumps(dict(detail), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        connection.execute(
            """
            INSERT INTO integration_request_events (event_id, request_id, occurred_at, event_type, detail_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), request_id, _utc_now(), event_type, detail_json),
        )
