"""Optional Foundation-backed paired-client request proof verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from integration_authority import IntegrationAuthorityStore


class FoundationDependencyUnavailable(RuntimeError):
    """The optional Shared Ecosystem Foundation package is not installed."""


class PairedProofRejected(RuntimeError):
    """A paired-client proof did not establish valid request provenance."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PairedProofDecision:
    request: dict[str, Any]
    client_id: str
    key_id: str
    proof_id: str
    idempotent: bool


def _foundation_types() -> tuple[Any, Any, Any]:
    try:
        from shared_ecosystem_contracts.authorization import (
            ClientRequestVerifier,
            GrantVerificationError,
            TrustedClient,
        )
    except ImportError as exc:
        raise FoundationDependencyUnavailable(
            "Install requirements-ecosystem.txt to enable paired-client proof verification."
        ) from exc
    return ClientRequestVerifier, GrantVerificationError, TrustedClient


class _AuthorityReplayStore:
    """Adapt the explicit ChatBoks store API to the Foundation replay protocol."""

    def __init__(self, authority_store: IntegrationAuthorityStore) -> None:
        self._authority_store = authority_store

    def consume(self, *, proof_id: str, nonce: str, request_id: str, expires_at: Any) -> str:
        return self._authority_store.consume_client_proof(
            proof_id=proof_id,
            nonce=nonce,
            request_id=request_id,
            expires_at=expires_at,
        )


class PairedClientProofGate:
    """Verify provenance using ChatBoks-owned keys and durable replay evidence.

    This gate does not authorize execution. Callers must still apply the local
    approval and capability policy before any work is started.
    """

    def __init__(
        self, authority_store: IntegrationAuthorityStore, *, target_application_id: str = "chatboks"
    ) -> None:
        if not target_application_id:
            raise ValueError("target_application_id is required")
        self.authority_store = authority_store
        self.target_application_id = target_application_id

    def verify(self, proof_token: str, request_payload: str) -> PairedProofDecision:
        verifier_type, verification_error, trusted_client_type = _foundation_types()
        trusted_records = self.authority_store.trusted_clients()
        if not trusted_records:
            self._record_denial("UNKNOWN_CLIENT")
            raise PairedProofRejected("UNKNOWN_CLIENT")
        trusted_clients = [
            trusted_client_type.from_public_bytes(record.client_id, record.key_id, record.public_key)
            for record in trusted_records
        ]
        verifier = verifier_type(
            target_application_id=self.target_application_id,
            trusted_clients=trusted_clients,
            replay_store=_AuthorityReplayStore(self.authority_store),
        )
        try:
            decision = verifier.verify(proof_token, request_payload)
        except verification_error as exc:
            self._record_denial(exc.code)
            raise PairedProofRejected(exc.code) from exc

        client_id = str(decision.subject["id"])
        key_id = str(decision.subject["keyId"])
        if self.authority_store.get_trusted_client(client_id, key_id) is None:
            self._record_denial("CLIENT_REVOKED")
            raise PairedProofRejected("CLIENT_REVOKED")

        self.authority_store.record_authorization(
            {
                "event": "paired_client_proof_verified",
                "outcome": "idempotent" if decision.idempotent else "accepted",
                "client_id": client_id,
                "key_id": key_id,
                "proof_id": decision.proof_id,
                "request_id": decision.request["requestId"],
                "correlation_id": decision.request["correlationId"],
                "request_payload_sha256": hashlib.sha256(
                    request_payload.encode("utf-8")
                ).hexdigest(),
            }
        )
        return PairedProofDecision(
            request=decision.request,
            client_id=client_id,
            key_id=key_id,
            proof_id=decision.proof_id,
            idempotent=decision.idempotent,
        )

    def _record_denial(self, code: str) -> None:
        self.authority_store.record_authorization(
            {
                "event": "paired_client_proof_rejected",
                "outcome": "denied",
                "code": code,
            }
        )
