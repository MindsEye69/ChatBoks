"""Tests for the request-owned integration worker boundary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import integration_execution_runner as runner
from integration_execution_runner import (
    IntegrationExecutionTerminationError,
    has_owned_integration_execution_worker,
    launch_integration_execution,
    run_execution,
    verify_integration_execution_worker,
)
from integration_executions import IntegrationExecutionRegistry, default_execution_registry_path
from integration_checkpoints import IntegrationCheckpointRegistry, default_checkpoint_registry_path
from integration_proofs import PairedProofDecision
from integration_requests import IntegrationRequestQueue, default_request_queue_path


def _dispatched_execution(tmp_path):
    queue = IntegrationRequestQueue(default_request_queue_path(tmp_path))
    request = queue.submit_verified(
        PairedProofDecision(
            request={
                "requestId": "request-runner-001",
                "contractVersion": "0.1.0",
                "ticketId": "CBX-001",
                "targetApplicationId": "chatboks",
                "capabilityId": "execution.lifecycle",
                "correlationId": "correlation-runner-001",
                "requestedAt": "2026-08-05T09:00:00Z",
                "input": {"prompt": "Implement the approved isolated integration task."},
            },
            client_id="dasdashboard",
            key_id="dash-client-key",
            proof_id="proof-runner-001",
            idempotent=False,
        )
    )
    queue.approve(request.request_id)
    registry = IntegrationExecutionRegistry(default_execution_registry_path(tmp_path))
    execution = registry.reserve(request.request_id)
    queue.mark_dispatched(request.request_id, "operator-session-001")
    return execution


def test_runner_executes_only_the_dispatched_request_and_persists_local_result(tmp_path):
    execution = _dispatched_execution(tmp_path)
    seen: dict[str, str] = {}

    class Agent:
        def execute(self, context: str) -> str:
            seen["context"] = context
            return "Implemented the request.\n>>> TASK_COMPLETE"

    completed = run_execution(
        project="chatboks",
        project_path=tmp_path,
        execution_id=execution.execution_id,
        config_path=None,
        agent_loader=lambda *_args: ("codex", Agent(), {}),
        context_builder=lambda *_args: "bounded project context",
    )

    assert completed.status == "succeeded"
    assert "bounded project context" in seen["context"]
    result = tmp_path / ".chatboks" / "integration-executions" / execution.execution_id / "result.md"
    assert result.read_text(encoding="utf-8").endswith(">>> TASK_COMPLETE")
    checkpoint = IntegrationCheckpointRegistry(default_checkpoint_registry_path(tmp_path)).get(execution.execution_id)
    assert checkpoint is not None
    assert checkpoint.state == "completed"
    assert checkpoint.result_status == "succeeded"
    assert [receipt.stage_id for receipt in IntegrationCheckpointRegistry(
        default_checkpoint_registry_path(tmp_path)
    ).stage_receipts(execution.execution_id)] == ["agent_loaded", "context_built", "result_written"]


def test_runner_marks_missing_terminal_signal_as_failed_without_leaking_output(tmp_path):
    execution = _dispatched_execution(tmp_path)

    class Agent:
        def execute(self, _context: str) -> str:
            return "Task output without the required completion signal."

    completed = run_execution(
        project="chatboks",
        project_path=tmp_path,
        execution_id=execution.execution_id,
        config_path=None,
        agent_loader=lambda *_args: ("codex", Agent(), {}),
        context_builder=lambda *_args: "bounded project context",
    )

    assert completed.status == "failed"
    assert completed.error_code == "missing_terminal_signal"


def test_launcher_binds_a_request_owned_worker_pid_before_returning(tmp_path, monkeypatch):
    execution = _dispatched_execution(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_popen(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(pid=5151, terminate=lambda: None)

    monkeypatch.setattr("integration_execution_runner.subprocess.Popen", fake_popen)

    pid = launch_integration_execution(
        project="chatboks",
        project_path=tmp_path,
        execution_id=execution.execution_id,
        config_path=None,
    )

    stored = IntegrationExecutionRegistry(default_execution_registry_path(tmp_path)).get(execution.execution_id)
    assert pid == 5151
    assert stored is not None
    assert stored.runner_pid == 5151
    assert calls[0]["cwd"] == tmp_path.resolve()
    assert calls[0]["shell"] is False
    assert calls[0]["command"][:2] == [
        runner.sys.executable,
        str(runner.Path(runner.__file__).resolve()),
    ]


def test_frozen_launcher_reenters_the_packaged_exe_with_worker_sentinel(tmp_path, monkeypatch):
    executable = tmp_path / "dist" / "ChatBoks.exe"
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(runner.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runner.sys, "executable", str(executable))

    command = runner._worker_command(
        project="chatboks",
        execution_id="execution-11111111-2222-3333-4444-555555555555",
        config_path=config_path,
    )

    assert command == [
        str(executable),
        runner.INTEGRATION_WORKER_FLAG,
        "--project",
        "chatboks",
        "--execution-id",
        "execution-11111111-2222-3333-4444-555555555555",
        "--config-path",
        str(config_path.resolve()),
    ]
    assert str(runner.Path(runner.__file__).resolve()) not in command


def test_worker_ownership_requires_the_exact_runner_script_and_execution_id(tmp_path, monkeypatch):
    execution = _dispatched_execution(tmp_path)
    registry = IntegrationExecutionRegistry(default_execution_registry_path(tmp_path))
    registry.attach_runner(execution.execution_id, 5151)
    execution = registry.get(execution.execution_id)
    assert execution is not None
    expected = f'python "{runner.Path(runner.__file__).resolve()}" --execution-id {execution.execution_id}'

    monkeypatch.setattr(runner, "_worker_command_line", lambda _pid: expected)
    assert has_owned_integration_execution_worker(execution) is True
    verify_integration_execution_worker(execution)

    monkeypatch.setattr(runner, "_worker_command_line", lambda _pid: "python unrelated_worker.py")
    assert has_owned_integration_execution_worker(execution) is False
    with pytest.raises(IntegrationExecutionTerminationError, match="not the expected"):
        verify_integration_execution_worker(execution)


def test_worker_ownership_accepts_frozen_exe_sentinel_and_exact_execution_id(tmp_path, monkeypatch):
    execution = _dispatched_execution(tmp_path)
    registry = IntegrationExecutionRegistry(default_execution_registry_path(tmp_path))
    registry.attach_runner(execution.execution_id, 5151)
    execution = registry.get(execution.execution_id)
    assert execution is not None
    executable = tmp_path / "dist" / "ChatBoks.exe"
    monkeypatch.setattr(runner.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runner.sys, "executable", str(executable))

    expected = (
        f'"{executable}" {runner.INTEGRATION_WORKER_FLAG} --project chatboks '
        f"--execution-id {execution.execution_id}"
    )
    monkeypatch.setattr(runner, "_worker_command_line", lambda _pid: expected)
    assert has_owned_integration_execution_worker(execution) is True
    verify_integration_execution_worker(execution)

    missing_sentinel = f'"{executable}" --project chatboks --execution-id {execution.execution_id}'
    monkeypatch.setattr(runner, "_worker_command_line", lambda _pid: missing_sentinel)
    assert has_owned_integration_execution_worker(execution) is False

    wrong_execution = (
        f'"{executable}" {runner.INTEGRATION_WORKER_FLAG} --project chatboks '
        f"--execution-id {execution.execution_id}-extra"
    )
    monkeypatch.setattr(runner, "_worker_command_line", lambda _pid: wrong_execution)
    assert has_owned_integration_execution_worker(execution) is False


def test_pre_agent_test_fault_is_explicit_and_one_shot(tmp_path, monkeypatch):
    monkeypatch.setenv(runner._TEST_FAULT_ENVIRONMENT, "exit_before_agent_once")

    assert runner._claim_pre_agent_test_fault(tmp_path) is True
    assert runner._claim_pre_agent_test_fault(tmp_path) is False
    assert (tmp_path / ".chatboks" / "integration-test-fault-pre-agent.once").exists()
