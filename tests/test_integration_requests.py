"""Tests for the local integration request approval queue."""

from __future__ import annotations

import sqlite3

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
        queue.mark_dispatched(queued.request_id, "session-queue-001")

    approved = queue.approve(queued.request_id, "Local operator reviewed scope.")
    assert approved.status == "approved"
    dispatched = queue.mark_dispatched(queued.request_id, "session-queue-001")
    assert dispatched.status == "dispatched"
    assert dispatched.dispatched_at is not None
    assert dispatched.execution_session_id == "session-queue-001"
    events = queue.events(queued.request_id)
    assert [event.event_type for event in events] == [
        "request_received",
        "request_approved",
        "request_dispatched",
    ]
    assert queue.events(queued.request_id, after_sequence=events[-1].sequence) == []

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


def test_queue_migrates_v1_database_with_execution_session_link(tmp_path):
    database = tmp_path / "integration-requests.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE integration_requests (
                request_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, capability_id TEXT NOT NULL,
                correlation_id TEXT NOT NULL, request_json TEXT NOT NULL, request_digest TEXT NOT NULL,
                client_id TEXT NOT NULL, key_id TEXT NOT NULL, proof_id TEXT NOT NULL UNIQUE,
                received_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'dispatched')),
                decided_at TEXT, decision_note TEXT, dispatched_at TEXT
            );
            PRAGMA user_version = 1;
            """
        )

    queue = IntegrationRequestQueue(database)
    queued = queue.submit_verified(_decision())

    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(integration_requests)")}
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2
    assert "execution_session_id" in columns
    assert queued.execution_session_id is None
