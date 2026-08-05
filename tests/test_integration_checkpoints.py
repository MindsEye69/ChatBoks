"""Tests for durable, non-replayable integration checkpoint receipts."""

import pytest

from integration_executions import IntegrationExecutionRegistry
from integration_proofs import PairedProofDecision
from integration_requests import IntegrationRequestQueue
from integration_checkpoints import (
    IntegrationCheckpointError,
    IntegrationCheckpointRegistry,
)


def test_checkpoint_records_agent_receipt_without_storing_result_text(tmp_path):
    registry = IntegrationCheckpointRegistry(tmp_path / "integration-checkpoints.sqlite3")
    prepared = registry.prepare("execution-checkpoint-001", "request-checkpoint-001")
    agent_loaded = registry.record_safe_stage(prepared.execution_id, "agent_loaded", "codex")
    context_built = registry.record_safe_stage(prepared.execution_id, "context_built", "private context")
    active = registry.begin_agent_step(prepared.execution_id)
    result_written = registry.record_safe_stage(active.execution_id, "result_written", "sensitive agent output")
    completed = registry.finish(active.execution_id, "succeeded", "sensitive agent output")

    assert prepared.state == "prepared"
    assert active.state == "in_progress"
    assert completed.state == "completed"
    assert completed.result_status == "succeeded"
    assert completed.result_digest is not None
    assert completed.result_digest not in "sensitive agent output"
    assert [receipt.stage_id for receipt in registry.stage_receipts(completed.execution_id)] == [
        agent_loaded.stage_id,
        context_built.stage_id,
        result_written.stage_id,
    ]
    assert registry.get(completed.execution_id) == completed


def test_uncertain_checkpoint_refuses_automatic_replay(tmp_path):
    registry = IntegrationCheckpointRegistry(tmp_path / "integration-checkpoints.sqlite3")
    checkpoint = registry.prepare("execution-checkpoint-002", "request-checkpoint-002")
    registry.begin_agent_step(checkpoint.execution_id)
    uncertain = registry.mark_uncertain(checkpoint.execution_id, "worker_not_verified")

    assert uncertain is not None
    assert uncertain.state == "uncertain"
    with pytest.raises(IntegrationCheckpointError, match="automatic replay is refused"):
        registry.prepare(checkpoint.execution_id, checkpoint.request_id)


def test_safe_stage_rejects_conflicting_retry_content(tmp_path):
    registry = IntegrationCheckpointRegistry(tmp_path / "integration-checkpoints.sqlite3")
    checkpoint = registry.prepare("execution-checkpoint-003", "request-checkpoint-003")
    registry.record_safe_stage(checkpoint.execution_id, "agent_loaded", "codex")

    with pytest.raises(IntegrationCheckpointError, match="conflicting content"):
        registry.record_safe_stage(checkpoint.execution_id, "agent_loaded", "claude")


def test_reopened_recovery_state_preserves_ticket_link_and_refuses_agent_replay(tmp_path):
    queue_path = tmp_path / "integration-requests.sqlite3"
    execution_path = tmp_path / "integration-executions.sqlite3"
    checkpoint_path = tmp_path / "integration-checkpoints.sqlite3"
    request = IntegrationRequestQueue(queue_path).submit_verified(
        PairedProofDecision(
            request={
                "requestId": "request-restart-001", "contractVersion": "0.1.0", "ticketId": "CBX-007",
                "targetApplicationId": "chatboks", "capabilityId": "execution.lifecycle",
                "correlationId": "correlation-restart-001", "requestedAt": "2026-08-05T09:00:00Z",
                "input": {"prompt": "Do not replay uncertain work."},
            },
            client_id="dasdashboard", key_id="dash-client-key", proof_id="proof-restart-001", idempotent=False,
        )
    )
    queue = IntegrationRequestQueue(queue_path)
    queue.approve(request.request_id)
    executions = IntegrationExecutionRegistry(execution_path)
    execution = executions.reserve(request.request_id)
    queue.mark_dispatched(request.request_id, "operator-session-001")
    executions.start(execution.execution_id, "worker-session-001")
    checkpoints = IntegrationCheckpointRegistry(checkpoint_path)
    checkpoints.prepare(execution.execution_id, request.request_id)
    checkpoints.begin_agent_step(execution.execution_id)

    reopened_queue = IntegrationRequestQueue(queue_path)
    reopened_executions = IntegrationExecutionRegistry(execution_path)
    reopened_checkpoints = IntegrationCheckpointRegistry(checkpoint_path)
    reopened_checkpoint = reopened_checkpoints.mark_uncertain(execution.execution_id, "restart_without_worker")

    assert reopened_queue.get(request.request_id).ticket_id == "CBX-007"
    assert reopened_executions.get_for_request(request.request_id).execution_id == execution.execution_id
    assert reopened_checkpoint is not None
    assert reopened_checkpoint.state == "uncertain"
    with pytest.raises(IntegrationCheckpointError, match="automatic replay is refused"):
        reopened_checkpoints.prepare(execution.execution_id, request.request_id)
