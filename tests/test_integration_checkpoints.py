"""Tests for durable, non-replayable integration checkpoint receipts."""

import pytest

from integration_checkpoints import (
    IntegrationCheckpointError,
    IntegrationCheckpointRegistry,
)


def test_checkpoint_records_agent_receipt_without_storing_result_text(tmp_path):
    registry = IntegrationCheckpointRegistry(tmp_path / "integration-checkpoints.sqlite3")
    prepared = registry.prepare("execution-checkpoint-001", "request-checkpoint-001")
    active = registry.begin_agent_step(prepared.execution_id)
    completed = registry.finish(active.execution_id, "succeeded", "sensitive agent output")

    assert prepared.state == "prepared"
    assert active.state == "in_progress"
    assert completed.state == "completed"
    assert completed.result_status == "succeeded"
    assert completed.result_digest is not None
    assert completed.result_digest not in "sensitive agent output"
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
