"""Enabled-path HTTP coverage for proof-verified integration request creation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request

from integration_authority import IntegrationAuthorityStore
from integration_requests import IntegrationRequestQueue, default_request_queue_path
from remote_control import RemoteAuth, RemoteBridgeServer, RemoteHandler, RemoteSession

try:
    from shared_ecosystem_contracts.authorization import ClientProofSigner, encode_execution_request
except ImportError:
    _CLIENT_PROOFS_AVAILABLE = False
else:
    _CLIENT_PROOFS_AVAILABLE = True


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


@unittest.skipUnless(
    _CLIENT_PROOFS_AVAILABLE,
    "requires the optional shared-ecosystem-contracts proof dependency",
)
class ProofVerifiedIntegrationRequestE2ETests(unittest.TestCase):
    def test_paired_proof_creates_only_one_pending_request_over_http(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory)
            authority = IntegrationAuthorityStore(project_path / "authority.sqlite3")
            signer = ClientProofSigner.generate("dasdashboard", "dash-client-key")
            authority.register_trusted_client(
                signer.client_id, signer.key_id, signer.public_key_bytes
            )

            now = datetime.now(UTC)
            execution_request = {
                "requestId": "request-http-e2e-001",
                "contractVersion": "0.1.0",
                "ticketId": "CBX-001",
                "targetApplicationId": "chatboks",
                "capabilityId": "execution.lifecycle",
                "correlationId": "correlation-http-e2e-001",
                "requestedAt": _timestamp(now),
                "input": {"prompt": "Inspect the current ticket without dispatching work."},
            }
            request_payload, request_digest, _ = encode_execution_request(execution_request)
            client_proof = signer.issue(
                {
                    "proofId": "proof-http-e2e-001",
                    "contractVersion": "0.4.0",
                    "subject": signer.subject_identity,
                    "targetApplicationId": "chatboks",
                    "requestId": execution_request["requestId"],
                    "correlationId": execution_request["correlationId"],
                    "requestDigest": request_digest,
                    "nonce": "nonce-http-e2e01",
                    "issuedAt": _timestamp(now),
                    "expiresAt": _timestamp(now + timedelta(minutes=1)),
                }
            )

            session = RemoteSession.__new__(RemoteSession)
            session.app = SimpleNamespace(proj_path=project_path)
            server = RemoteBridgeServer(
                ("127.0.0.1", 0), RemoteHandler, session, RemoteAuth("bridge-token")
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            endpoint = f"http://{host}:{port}/api/integration/v1/requests"
            body = json.dumps(
                {"clientProof": client_proof, "requestPayload": request_payload}
            ).encode("utf-8")

            try:
                with patch("remote_control.IntegrationAuthorityStore", return_value=authority):
                    responses = []
                    for _attempt in range(2):
                        request = urllib.request.Request(
                            endpoint,
                            data=body,
                            headers={
                                "Authorization": "Bearer bridge-token",
                                "Content-Type": "application/json",
                            },
                            method="POST",
                        )
                        with urllib.request.urlopen(request, timeout=5) as response:
                            self.assertEqual(response.status, 202)
                            responses.append(json.loads(response.read().decode("utf-8")))
                    events_request = urllib.request.Request(
                        f"{endpoint}/request-http-e2e-001/events?after=0",
                        headers={"Authorization": "Bearer bridge-token"},
                    )
                    with urllib.request.urlopen(events_request, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        event_payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(responses[0], responses[1])
            response_request = responses[0]["request"]
            self.assertEqual(response_request["request_id"], execution_request["requestId"])
            self.assertEqual(response_request["status"], "pending")
            self.assertEqual(response_request["client"], {"id": "dasdashboard", "key_id": "dash-client-key"})
            self.assertNotIn("input", response_request)
            self.assertNotIn("proof_id", response_request)
            self.assertEqual(event_payload["schema"], "chatboks.integration-request-event-list/v1")
            self.assertEqual([event["type"] for event in event_payload["events"]], ["request_received"])
            self.assertNotIn("detail", event_payload["events"][0])
            self.assertNotIn("proof_id", event_payload["events"][0])

            queue = IntegrationRequestQueue(default_request_queue_path(project_path))
            queued_requests = queue.list()
            self.assertEqual(len(queued_requests), 1)
            queued = queued_requests[0]
            self.assertEqual(queued.status, "pending")
            self.assertEqual(queued.request, execution_request)
            self.assertIsNone(queued.decided_at)
            self.assertIsNone(queued.dispatched_at)
            self.assertTrue(authority.verify_audit_chain())
            self.assertNotIn(client_proof, json.dumps([record.document for record in authority.audit_records()]))


if __name__ == "__main__":
    unittest.main()
