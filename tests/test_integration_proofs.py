"""Integration tests for the optional paired-client proof gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from integration_authority import IntegrationAuthorityStore
from integration_proofs import PairedClientProofGate


def test_paired_client_proof_uses_local_keys_replay_and_audit(tmp_path):
    authorization = pytest.importorskip("shared_ecosystem_contracts.authorization")
    signer = authorization.ClientProofSigner.generate("dasdashboard", "dash-client-key")
    store = IntegrationAuthorityStore(tmp_path / "authority.sqlite3")
    store.register_trusted_client("dasdashboard", "dash-client-key", signer.public_key_bytes)
    request = {
        "requestId": "request-chatboks-proof",
        "contractVersion": "0.1.0",
        "ticketId": "CBX-001",
        "targetApplicationId": "chatboks",
        "capabilityId": "execution.lifecycle",
        "correlationId": "correlation-chatboks-proof",
        "requestedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "input": {"operation": "create"},
    }
    payload, digest, _ = authorization.encode_execution_request(request)
    proof = signer.issue(
        {
            "proofId": "proof-chatboks-client",
            "contractVersion": "0.4.0",
            "subject": signer.subject_identity,
            "targetApplicationId": "chatboks",
            "requestId": request["requestId"],
            "correlationId": request["correlationId"],
            "requestDigest": digest,
            "nonce": "R48f0wD25mYq_sNu",
            "issuedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "expiresAt": (datetime.now(UTC) + timedelta(minutes=1))
            .isoformat()
            .replace("+00:00", "Z"),
        }
    )

    first = PairedClientProofGate(store).verify(proof, payload)
    retry = PairedClientProofGate(IntegrationAuthorityStore(store.database_path)).verify(proof, payload)

    assert first.client_id == "dasdashboard"
    assert first.idempotent is False
    assert retry.idempotent is True
    assert [record.document["event"] for record in store.audit_records()][-2:] == [
        "paired_client_proof_verified",
        "paired_client_proof_verified",
    ]
