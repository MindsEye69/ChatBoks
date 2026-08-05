"""Tests for ChatBoks' local integration authority state."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from integration_authority import AuthorityStoreError, IntegrationAuthorityStore


def test_trusted_client_pairing_is_durable_and_refuses_silent_key_replacement(tmp_path: Path):
    database = tmp_path / "authority.sqlite3"
    store = IntegrationAuthorityStore(database)
    first_key = bytes(range(32))
    paired = store.register_trusted_client("das-dashboard", "primary-2026", first_key)

    assert paired.public_key == first_key
    assert paired.fingerprint == hashlib.sha256(first_key).hexdigest()
    assert store.get_trusted_client("das-dashboard", "primary-2026") == paired
    assert store.register_trusted_client("das-dashboard", "primary-2026", first_key) == paired
    with pytest.raises(AuthorityStoreError, match="Refusing to replace"):
        store.register_trusted_client("das-dashboard", "primary-2026", bytes(reversed(first_key)))

    reopened = IntegrationAuthorityStore(database)
    assert reopened.get_trusted_client("das-dashboard", "primary-2026") == paired
    assert reopened.verify_audit_chain()


def test_client_revocation_preserves_history_and_disables_key(tmp_path: Path):
    store = IntegrationAuthorityStore(tmp_path / "authority.sqlite3")
    store.register_trusted_client("das-dashboard", "primary-2026", bytes(range(32)))

    assert store.revoke_trusted_client("das-dashboard", "primary-2026") is True
    assert store.revoke_trusted_client("das-dashboard", "primary-2026") is False
    assert store.get_trusted_client("das-dashboard", "primary-2026") is None
    historical = store.get_trusted_client(
        "das-dashboard", "primary-2026", include_revoked=True
    )
    assert historical is not None
    assert historical.revoked_at is not None
    assert [record.document["event"] for record in store.audit_records()] == [
        "trusted_client_paired",
        "trusted_client_revoked",
    ]


def test_grant_revocations_are_durable_and_cannot_be_replaced(tmp_path: Path):
    database = tmp_path / "authority.sqlite3"
    store = IntegrationAuthorityStore(database)
    record = {"grant_id": "grant-001", "issuer": "chatboks", "signature": "placeholder"}

    assert store.record_grant_revocation("grant-001", record) is True
    assert store.record_grant_revocation("grant-001", record) is False
    assert store.is_grant_revoked("grant-001") is True
    with pytest.raises(AuthorityStoreError, match="Refusing to replace"):
        store.record_grant_revocation("grant-001", {**record, "signature": "other"})

    reopened = IntegrationAuthorityStore(database)
    assert reopened.is_grant_revoked("grant-001") is True
    assert reopened.verify_audit_chain()


def test_authorization_audit_is_chained_and_rejects_unsafe_documents(tmp_path: Path):
    store = IntegrationAuthorityStore(tmp_path / "authority.sqlite3")
    first = store.record_authorization(
        {"event": "authorization_decision", "outcome": "approved", "request_digest": "a" * 64}
    )
    second = store.record_authorization(
        {"event": "execution_finished", "outcome": "completed", "request_digest": "a" * 64}
    )

    assert second.previous_hash == first.record_hash
    assert store.verify_audit_chain() is True
    with pytest.raises(AuthorityStoreError, match="not JSON-safe"):
        store.record_authorization({"event": object()})
    with pytest.raises(AuthorityStoreError, match="exceeds"):
        store.record_authorization({"event": "authorization_decision", "detail": "x" * 40000})
