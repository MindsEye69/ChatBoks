"""Coverage for the standalone structured ticket-execution input contract."""

from __future__ import annotations

from copy import deepcopy

import pytest

from integration_proofs import PairedProofDecision
from integration_requests import IntegrationRequestError, IntegrationRequestQueue
from ticket_execution import TICKET_EXECUTION_SCHEMA, parse_ticket_execution


def _request(
    *,
    request_id: str = "request-ticket-001",
    correlation_id: str = "correlation-ticket-001",
    idempotency_key: str = "ticket-run-001",
) -> dict[str, object]:
    return {
        "requestId": request_id,
        "contractVersion": "0.1.0",
        "ticketId": "CBX-002",
        "targetApplicationId": "chatboks",
        "capabilityId": "execution.lifecycle",
        "correlationId": correlation_id,
        "requestedAt": "2026-08-05T09:00:00Z",
        "input": {
            "ticketExecution": {
                "schema": TICKET_EXECUTION_SCHEMA,
                "objective": "Add a narrowly scoped ticket adapter.",
                "constraints": ["Keep ChatBoks standalone.", "Do not use a shared database."],
                "contextReferences": ["docs/integration-authority.md"],
                "requestedCapabilities": ["execution.lifecycle"],
                "approvalPolicy": "local_operator_required",
                "verificationCriteria": ["Run the focused tests."],
                "budget": {"maxSteps": 6, "maxRuntimeSeconds": 300},
                "idempotencyKey": idempotency_key,
            }
        },
    }


def _decision(request: dict[str, object], proof_id: str) -> PairedProofDecision:
    return PairedProofDecision(
        request=request,
        client_id="dasdashboard",
        key_id="dash-client-key",
        proof_id=proof_id,
        idempotent=False,
    )


def test_structured_ticket_is_normalized_and_rendered_as_untrusted_task_material():
    ticket = parse_ticket_execution(_request())

    assert ticket is not None
    assert ticket.objective == "Add a narrowly scoped ticket adapter."
    assert ticket.requested_capabilities == ("execution.lifecycle",)
    assert "[TICKET OBJECTIVE]" in ticket.render_task_material()
    assert "[VERIFICATION CRITERIA]" in ticket.render_task_material()


def test_structured_ticket_idempotency_deduplicates_retried_delivery(tmp_path):
    queue = IntegrationRequestQueue(tmp_path / "integration-requests.sqlite3")
    first_request = _request()
    first = queue.submit_verified(_decision(first_request, "proof-ticket-001"))
    retry = queue.submit_verified(
        _decision(
            _request(request_id="request-ticket-002", correlation_id="correlation-ticket-002"),
            "proof-ticket-002",
        )
    )

    assert retry == first
    assert retry.idempotency_key == "ticket-run-001"
    assert len(queue.list()) == 1


def test_structured_ticket_rejects_a_changed_payload_reusing_an_idempotency_key(tmp_path):
    queue = IntegrationRequestQueue(tmp_path / "integration-requests.sqlite3")
    queue.submit_verified(_decision(_request(), "proof-ticket-001"))
    conflicting = deepcopy(_request(request_id="request-ticket-002", correlation_id="correlation-ticket-002"))
    conflicting["input"]["ticketExecution"]["objective"] = "Perform different work."

    with pytest.raises(IntegrationRequestError, match="different ticket payload"):
        queue.submit_verified(_decision(conflicting, "proof-ticket-002"))


def test_structured_ticket_requires_the_declared_execution_capability(tmp_path):
    queue = IntegrationRequestQueue(tmp_path / "integration-requests.sqlite3")
    invalid = deepcopy(_request())
    invalid["input"]["ticketExecution"]["requestedCapabilities"] = ["workspace.read"]

    with pytest.raises(IntegrationRequestError, match="exactly the requested capabilityId"):
        queue.submit_verified(_decision(invalid, "proof-ticket-001"))


def test_structured_ticket_rejects_unused_declared_capabilities(tmp_path):
    queue = IntegrationRequestQueue(tmp_path / "integration-requests.sqlite3")
    invalid = deepcopy(_request())
    invalid["input"]["ticketExecution"]["requestedCapabilities"].append("workspace.read")

    with pytest.raises(IntegrationRequestError, match="exactly the requested capabilityId"):
        queue.submit_verified(_decision(invalid, "proof-ticket-001"))


def test_queue_rejects_a_capability_chatboks_cannot_authorize(tmp_path):
    queue = IntegrationRequestQueue(tmp_path / "integration-requests.sqlite3")
    invalid = deepcopy(_request())
    invalid["capabilityId"] = "workspace.read"
    invalid["input"]["ticketExecution"]["requestedCapabilities"] = ["workspace.read"]

    with pytest.raises(IntegrationRequestError, match="does not support integration capability"):
        queue.submit_verified(_decision(invalid, "proof-ticket-001"))
