"""Tests for the local integration request approval queue."""

from __future__ import annotations

import pytest

from integration_proofs import PairedProofDecision
from integration_requests import IntegrationRequestError, IntegrationRequestQueue


def _decision(request_id: str = "request-queue-001") -> PairedProofDecision:
    return PairedProofDecision(
        request={
            "requestId": request_id, "contractVersion": "0.1.0", "ticketId": "CBX-001",
            "targetApplicationId": "chatboks", "capabilityId": "execution.lifecycle",
            "correlationId": "correlation-queue-001", "requestedAt": "2026-08-05T09:00:00Z",
            "input": {"prompt": "Plan a safe change."},
        },
        client_id="dasdashboard", key_id="dash-client-key", proof_id="proof-queue-001", idempotent=False,
    )


def test_queue_requires_explicit_approval_before_dispatch_and_is_durable(tmp_path):
    database = tmp_path / "integration-requests.sqlite3"
    queue = IntegrationRequestQueue(database)
    queued = queue.submit_verified(_decision())

    assert queued.status == "pending"
    assert queue.submit_verified(_decision()) == queued
    with pytest.raises(IntegrationRequestError, match="Only an explicitly approved"):
        queue.mark_dispatched(queued.request_id)

    approved = queue.approve(queued.request_id, "Local operator reviewed scope.")
    assert approved.status == "approved"
    dispatched = queue.mark_dispatched(queued.request_id)
    assert dispatched.status == "dispatched"
    assert dispatched.dispatched_at is not None

    reopened = IntegrationRequestQueue(database)
    assert reopened.get(queued.request_id) == dispatched
    assert [item.request_id for item in reopened.list(status="dispatched")] == [queued.request_id]


def test_queue_rejects_conflicts_and_terminal_transitions(tmp_path):
    queue = IntegrationRequestQueue(tmp_path / "integration-requests.sqlite3")
    queued = queue.submit_verified(_decision())

    conflicting = PairedProofDecision(
        request={**queued.request, "input": {"prompt": "Different work."}},
        client_id=queued.client_id, key_id=queued.key_id, proof_id=queued.proof_id, idempotent=False,
    )
    with pytest.raises(IntegrationRequestError, match="different request or proof"):
        queue.submit_verified(conflicting)
    rejected = queue.reject(queued.request_id, "Scope is not approved.")
    assert rejected.status == "rejected"
    with pytest.raises(IntegrationRequestError, match="already rejected"):
        queue.approve(queued.request_id)
