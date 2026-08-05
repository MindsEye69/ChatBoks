"""Durable, local approval queue for verified integration requests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from integration_proofs import PairedProofDecision


_QUEUE_SCHEMA_VERSION = 1
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_NOTE_BYTES = 1_000
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
    client_id: str
    key_id: str
    proof_id: str
    received_at: str
    status: str
    decided_at: str | None
    decision_note: str | None
    dispatched_at: str | None


def default_request_queue_path(project_path: Path) -> Path:
    return project_path / ".chatboks" / "integration-requests.sqlite3"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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

    def _initialize(self) -> None:
        with self._connect() as connection:
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
                    client_id TEXT NOT NULL, key_id TEXT NOT NULL, proof_id TEXT NOT NULL UNIQUE,
                    received_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'dispatched')),
                    decided_at TEXT, decision_note TEXT, dispatched_at TEXT
                );
                CREATE TABLE IF NOT EXISTS integration_request_events (
                    event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    event_type TEXT NOT NULL, detail_json TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES integration_requests(request_id)
                );
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
            client_id=str(row["client_id"]),
            key_id=str(row["key_id"]),
            proof_id=str(row["proof_id"]),
            received_at=str(row["received_at"]),
            status=str(row["status"]),
            decided_at=str(row["decided_at"]) if row["decided_at"] is not None else None,
            decision_note=str(row["decision_note"]) if row["decision_note"] is not None else None,
            dispatched_at=str(row["dispatched_at"]) if row["dispatched_at"] is not None else None,
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
        digest = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
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
            connection.execute(
                """
                INSERT INTO integration_requests (
                    request_id, ticket_id, capability_id, correlation_id, request_json, request_digest,
                    client_id, key_id, proof_id, received_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (request_id, ticket_id, capability_id, correlation_id, request_json, digest,
                 decision.client_id, decision.key_id, decision.proof_id, received_at),
            )
            self._append_event(
                connection, request_id, "request_received",
                {"client_id": decision.client_id, "key_id": decision.key_id,
                 "proof_id": decision.proof_id, "request_digest": digest},
            )
        return QueuedIntegrationRequest(
            request_id, ticket_id, capability_id, correlation_id, request, decision.client_id,
            decision.key_id, decision.proof_id, received_at, "pending", None, None, None
        )

    def get(self, request_id: str) -> QueuedIntegrationRequest | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM integration_requests WHERE request_id = ?", (request_id,)).fetchone()
        return self._from_row(row) if row is not None else None

    def list(self, *, status: str | None = None) -> list[QueuedIntegrationRequest]:
        if status is not None and status not in _STATUSES:
            raise IntegrationRequestError("Unknown integration request status.")
        query, params = "SELECT * FROM integration_requests", ()
        if status is not None:
            query, params = f"{query} WHERE status = ?", (status,)
        with self._connect() as connection:
            rows = connection.execute(f"{query} ORDER BY received_at DESC", params).fetchall()
        return [self._from_row(row) for row in rows]

    def approve(self, request_id: str, note: str = "") -> QueuedIntegrationRequest:
        return self._decide(request_id, "approved", note)

    def reject(self, request_id: str, note: str = "") -> QueuedIntegrationRequest:
        return self._decide(request_id, "rejected", note)

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
            connection.execute(
                "UPDATE integration_requests SET status = ?, decided_at = ?, decision_note = ? WHERE request_id = ?",
                (outcome, decided_at, note or None, request_id),
            )
            self._append_event(connection, request_id, f"request_{outcome}", {"note": note})
        return replace(current, status=outcome, decided_at=decided_at, decision_note=note or None)

    def mark_dispatched(self, request_id: str) -> QueuedIntegrationRequest:
        """Mark an approved request dispatched immediately before local routing."""
        dispatched_at = _utc_now()
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM integration_requests WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise IntegrationRequestError("Integration request was not found.")
            current = self._from_row(row)
            if current.status != "approved":
                raise IntegrationRequestError("Only an explicitly approved integration request may be dispatched.")
            connection.execute(
                "UPDATE integration_requests SET status = 'dispatched', dispatched_at = ? WHERE request_id = ?",
                (dispatched_at, request_id),
            )
            self._append_event(connection, request_id, "request_dispatched", {})
        return replace(current, status="dispatched", dispatched_at=dispatched_at)

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
