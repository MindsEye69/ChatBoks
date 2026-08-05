"""Tests for the local-only integration request commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from integration_proofs import PairedProofDecision
from integration_requests import IntegrationRequestQueue
from orchestrator import Chatboks


def _app(root: Path) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.proj_path = root
    app.stream = MagicMock()
    app.handle_user_input = MagicMock()
    return app


def _queue_request(root: Path) -> str:
    request = IntegrationRequestQueue(root / ".chatboks" / "integration-requests.sqlite3").submit_verified(
        PairedProofDecision(
            request={
                "requestId": "request-command-001",
                "contractVersion": "0.1.0",
                "ticketId": "CBX-001",
                "targetApplicationId": "chatboks",
                "capabilityId": "execution.lifecycle",
                "correlationId": "correlation-command-001",
                "requestedAt": "2026-08-05T09:00:00Z",
                "input": {"prompt": "Review the integration task."},
            },
            client_id="dasdashboard",
            key_id="dash-client-key",
            proof_id="proof-command-001",
            idempotent=False,
        )
    )
    return request.request_id


def test_remote_origin_cannot_approve_or_dispatch_integration_request(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)

    Chatboks.handle_integration_command(app, f"/integration approve {request_id}", source="remote")

    queued = app.integration_request_queue().get(request_id)
    assert queued is not None
    assert queued.status == "pending"
    assert "require a local terminal or desktop operator" in app.stream.system.call_args.args[0]


def test_local_operator_must_approve_before_dispatching_to_router(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)

    Chatboks.handle_integration_command(app, f"/integration approve {request_id}", source="terminal")
    Chatboks.handle_integration_command(app, f"/integration dispatch {request_id}", source="terminal")

    queued = app.integration_request_queue().get(request_id)
    assert queued is not None
    assert queued.status == "dispatched"
    routed_prompt = app.handle_user_input.call_args.args[0]
    assert "[VERIFIED INTEGRATION REQUEST]" in routed_prompt
    assert "Review the integration task." in routed_prompt
    assert app.handle_user_input.call_args.kwargs["source"] == "integration_dispatch"
