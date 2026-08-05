"""Durable, ChatBoks-owned trust and authorization evidence storage."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
import uuid


AUTHORITY_SCHEMA_VERSION = 1
ED25519_PUBLIC_KEY_BYTES = 32
_ZERO_HASH = "0" * 64
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_DOCUMENT_BYTES = 32 * 1024
_MAX_JSON_DEPTH = 12
_MAX_JSON_ITEMS = 256


class AuthorityStoreError(ValueError):
    """Raised when untrusted data cannot safely become authority state."""


@dataclass(frozen=True)
class TrustedClient:
    client_id: str
    key_id: str
    public_key: bytes
    fingerprint: str
    paired_at: str
    revoked_at: str | None


@dataclass(frozen=True)
class AuditRecord:
    sequence: int
    audit_id: str
    recorded_at: str
    document: dict[str, Any]
    previous_hash: str
    record_hash: str


def default_authority_database_path() -> Path:
    """Return the per-user authority database path used by ChatBoks."""
    return Path.home() / ".chatboks" / "integration_authority.sqlite3"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise AuthorityStoreError(
            f"{label} must be 1-128 characters of letters, digits, '.', '_', ':', or '-'."
        )
    return value


def _json_value(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_JSON_DEPTH:
        raise AuthorityStoreError("Authority document nesting exceeds the supported limit.")
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise AuthorityStoreError("Authority documents cannot contain non-finite numbers.")
        return value
    if isinstance(value, Mapping):
        if len(value) > _MAX_JSON_ITEMS:
            raise AuthorityStoreError("Authority document object has too many fields.")
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AuthorityStoreError("Authority document object keys must be strings.")
            normalized[key] = _json_value(item, depth + 1)
        return normalized
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_JSON_ITEMS:
            raise AuthorityStoreError("Authority document array has too many items.")
        return [_json_value(item, depth + 1) for item in value]
    raise AuthorityStoreError(f"Authority document value is not JSON-safe: {type(value).__name__}.")


def _canonical_document(document: Mapping[str, Any], *, label: str) -> str:
    if not isinstance(document, Mapping):
        raise AuthorityStoreError(f"{label} must be a JSON object.")
    normalized = _json_value(document)
    assert isinstance(normalized, dict)
    encoded = json.dumps(
        normalized, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    if len(encoded.encode("utf-8")) > _MAX_DOCUMENT_BYTES:
        raise AuthorityStoreError(f"{label} exceeds the {_MAX_DOCUMENT_BYTES}-byte limit.")
    return encoded


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class IntegrationAuthorityStore:
    """SQLite-backed local authority state for optional paired integrations.

    The store has no network surface and deliberately stores neither private
    keys nor bearer tokens. It persists already-validated revocation evidence;
    signature validation remains with the contract verifier.
    """

    def __init__(self, database_path: Path | str | None = None) -> None:
        path = Path(database_path) if database_path is not None else default_authority_database_path()
        self.database_path = path.expanduser().resolve()
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
            if version > AUTHORITY_SCHEMA_VERSION:
                raise AuthorityStoreError(
                    f"Authority schema {version} is newer than this ChatBoks version supports."
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trusted_clients (
                    client_id TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    public_key BLOB NOT NULL CHECK(length(public_key) = 32),
                    fingerprint TEXT NOT NULL,
                    paired_at TEXT NOT NULL,
                    revoked_at TEXT,
                    PRIMARY KEY (client_id, key_id)
                );
                CREATE TABLE IF NOT EXISTS grant_revocations (
                    grant_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    record_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS authorization_audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL UNIQUE,
                    recorded_at TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE
                );
                """
            )
            if version == 0:
                connection.execute(f"PRAGMA user_version = {AUTHORITY_SCHEMA_VERSION}")

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
    def _trusted_client_from_row(row: sqlite3.Row) -> TrustedClient:
        return TrustedClient(
            client_id=str(row["client_id"]),
            key_id=str(row["key_id"]),
            public_key=bytes(row["public_key"]),
            fingerprint=str(row["fingerprint"]),
            paired_at=str(row["paired_at"]),
            revoked_at=str(row["revoked_at"]) if row["revoked_at"] is not None else None,
        )

    def register_trusted_client(
        self, client_id: str, key_id: str, public_key: bytes | bytearray | memoryview
    ) -> TrustedClient:
        """Persist a paired Ed25519 public key without allowing silent rotation."""
        client_id = _require_identifier(client_id, "client_id")
        key_id = _require_identifier(key_id, "key_id")
        if not isinstance(public_key, (bytes, bytearray, memoryview)):
            raise AuthorityStoreError("public_key must contain raw Ed25519 public-key bytes.")
        key_bytes = bytes(public_key)
        if len(key_bytes) != ED25519_PUBLIC_KEY_BYTES:
            raise AuthorityStoreError(
                f"public_key must contain exactly {ED25519_PUBLIC_KEY_BYTES} bytes."
            )

        fingerprint = hashlib.sha256(key_bytes).hexdigest()
        paired_at = _utc_now()
        with self._write_transaction() as connection:
            row = connection.execute(
                """
                SELECT client_id, key_id, public_key, fingerprint, paired_at, revoked_at
                FROM trusted_clients WHERE client_id = ? AND key_id = ?
                """,
                (client_id, key_id),
            ).fetchone()
            if row is not None:
                existing = self._trusted_client_from_row(row)
                if existing.revoked_at is not None:
                    raise AuthorityStoreError(
                        "This paired key is revoked; create a new key id after explicit re-pairing."
                    )
                if existing.public_key != key_bytes:
                    raise AuthorityStoreError(
                        "Refusing to replace an existing paired public key without explicit re-pairing."
                    )
                return existing
            connection.execute(
                """
                INSERT INTO trusted_clients
                    (client_id, key_id, public_key, fingerprint, paired_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (client_id, key_id, key_bytes, fingerprint, paired_at),
            )
            self._append_audit_locked(
                connection,
                {
                    "event": "trusted_client_paired",
                    "client_id": client_id,
                    "key_id": key_id,
                    "key_fingerprint": fingerprint,
                },
            )
        return TrustedClient(client_id, key_id, key_bytes, fingerprint, paired_at, None)

    def get_trusted_client(
        self, client_id: str, key_id: str, *, include_revoked: bool = False
    ) -> TrustedClient | None:
        client_id = _require_identifier(client_id, "client_id")
        key_id = _require_identifier(key_id, "key_id")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT client_id, key_id, public_key, fingerprint, paired_at, revoked_at
                FROM trusted_clients WHERE client_id = ? AND key_id = ?
                """,
                (client_id, key_id),
            ).fetchone()
        if row is None:
            return None
        client = self._trusted_client_from_row(row)
        return client if include_revoked or client.revoked_at is None else None

    def revoke_trusted_client(self, client_id: str, key_id: str) -> bool:
        """Logically revoke a paired key while preserving its trust history."""
        client_id = _require_identifier(client_id, "client_id")
        key_id = _require_identifier(key_id, "key_id")
        revoked_at = _utc_now()
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT fingerprint, revoked_at FROM trusted_clients WHERE client_id = ? AND key_id = ?",
                (client_id, key_id),
            ).fetchone()
            if row is None or row["revoked_at"] is not None:
                return False
            connection.execute(
                "UPDATE trusted_clients SET revoked_at = ? WHERE client_id = ? AND key_id = ?",
                (revoked_at, client_id, key_id),
            )
            self._append_audit_locked(
                connection,
                {
                    "event": "trusted_client_revoked",
                    "client_id": client_id,
                    "key_id": key_id,
                    "key_fingerprint": str(row["fingerprint"]),
                },
            )
        return True

    def record_grant_revocation(self, grant_id: str, signed_record: Mapping[str, Any]) -> bool:
        """Persist caller-validated revocation evidence without overwriting it."""
        grant_id = _require_identifier(grant_id, "grant_id")
        record_json = _canonical_document(signed_record, label="signed_record")
        record = json.loads(record_json)
        if record.get("grant_id") is not None and record["grant_id"] != grant_id:
            raise AuthorityStoreError("signed_record grant_id does not match the requested grant_id.")
        record_digest = _sha256_hex(record_json)
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT record_digest FROM grant_revocations WHERE grant_id = ?", (grant_id,)
            ).fetchone()
            if row is not None:
                if str(row["record_digest"]) != record_digest:
                    raise AuthorityStoreError("Refusing to replace an existing grant-revocation record.")
                return False
            connection.execute(
                """
                INSERT INTO grant_revocations (grant_id, recorded_at, record_json, record_digest)
                VALUES (?, ?, ?, ?)
                """,
                (grant_id, _utc_now(), record_json, record_digest),
            )
            self._append_audit_locked(
                connection,
                {
                    "event": "grant_revoked",
                    "grant_id": grant_id,
                    "revocation_record_digest": record_digest,
                },
            )
        return True

    def is_grant_revoked(self, grant_id: str) -> bool:
        grant_id = _require_identifier(grant_id, "grant_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM grant_revocations WHERE grant_id = ?", (grant_id,)
            ).fetchone()
        return row is not None

    def record_authorization(self, document: Mapping[str, Any]) -> AuditRecord:
        """Append an authorization decision or execution result to the audit chain."""
        with self._write_transaction() as connection:
            return self._append_audit_locked(connection, document)

    def audit_sink(self, document: Mapping[str, Any]) -> None:
        """Adapter shape for the Foundation verifier's audit callback."""
        self.record_authorization(document)

    def _append_audit_locked(
        self, connection: sqlite3.Connection, document: Mapping[str, Any]
    ) -> AuditRecord:
        document_json = _canonical_document(document, label="authorization audit document")
        last = connection.execute(
            "SELECT record_hash FROM authorization_audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = str(last["record_hash"]) if last is not None else _ZERO_HASH
        audit_id = str(uuid.uuid4())
        recorded_at = _utc_now()
        material = {
            "audit_id": audit_id,
            "recorded_at": recorded_at,
            "document": json.loads(document_json),
            "previous_hash": previous_hash,
        }
        material_json = json.dumps(
            material, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        record_hash = _sha256_hex(material_json)
        cursor = connection.execute(
            """
            INSERT INTO authorization_audit
                (audit_id, recorded_at, document_json, previous_hash, record_hash)
            VALUES (?, ?, ?, ?, ?)
            """,
            (audit_id, recorded_at, document_json, previous_hash, record_hash),
        )
        return AuditRecord(
            sequence=int(cursor.lastrowid),
            audit_id=audit_id,
            recorded_at=recorded_at,
            document=json.loads(document_json),
            previous_hash=previous_hash,
            record_hash=record_hash,
        )

    def audit_records(self) -> list[AuditRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence, audit_id, recorded_at, document_json, previous_hash, record_hash
                FROM authorization_audit ORDER BY sequence
                """
            ).fetchall()
        return [
            AuditRecord(
                sequence=int(row["sequence"]),
                audit_id=str(row["audit_id"]),
                recorded_at=str(row["recorded_at"]),
                document=json.loads(str(row["document_json"])),
                previous_hash=str(row["previous_hash"]),
                record_hash=str(row["record_hash"]),
            )
            for row in rows
        ]

    def verify_audit_chain(self) -> bool:
        """Check the local chain for corruption or partial modification.

        This is not a defence against a local attacker who can rewrite the
        complete database; it is intentionally not represented as one.
        """
        previous_hash = _ZERO_HASH
        for record in self.audit_records():
            if record.previous_hash != previous_hash:
                return False
            material = {
                "audit_id": record.audit_id,
                "recorded_at": record.recorded_at,
                "document": record.document,
                "previous_hash": record.previous_hash,
            }
            material_json = json.dumps(
                material, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
            )
            if _sha256_hex(material_json) != record.record_hash:
                return False
            previous_hash = record.record_hash
        return True
