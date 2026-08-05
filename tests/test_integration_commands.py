"""Tests for the local-only integration request commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from integration_proofs import PairedProofDecision
from integration_execution_runner import IntegrationExecutionTerminationError
from integration_checkpoints import IntegrationCheckpointRegistry, default_checkpoint_registry_path
from integration_requests import IntegrationRequestQueue
from orchestrator import Chatboks


def _app(root: Path) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.proj_path = root
    app.state = {"session": "session-command-001"}
    app.stream = MagicMock()
    app.handle_user_input = MagicMock()
    app.start_integration_execution = MagicMock(return_value=4242)
    app.verify_integration_execution = MagicMock()
    app.cancel_integration_execution = MagicMock()
    app.integration_execution_is_owned = MagicMock(return_value=False)
    return app


def _queue_request(root: Path, *, structured: bool = False) -> str:
    task_input = (
        {
            "ticketExecution": {
                "schema": "chatboks.ticket-execution/v1",
                "objective": "Review the bounded ticket execution.",
                "constraints": ["Keep the worker isolated."],
                "contextReferences": ["docs/integration-authority.md"],
                "requestedCapabilities": ["execution.lifecycle"],
                "approvalPolicy": "local_operator_required",
                "verificationCriteria": ["Confirm the worker starts."],
                "budget": {"maxSteps": 4, "maxRuntimeSeconds": 120},
                "idempotencyKey": "command-ticket-001",
            }
        }
        if structured
        else {"prompt": "Review the integration task."}
    )
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
                "input": task_input,
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


def test_remote_origin_cannot_revoke_integration_approval(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)
    app.integration_request_queue().approve(request_id)

    Chatboks.handle_integration_command(app, f"/integration revoke {request_id}", source="remote")

    queued = app.integration_request_queue().get(request_id)
    assert queued is not None
    assert queued.status == "approved"
    assert "require a local terminal or desktop operator" in app.stream.system.call_args.args[0]


def test_local_operator_must_approve_before_dispatching_to_an_isolated_runner(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)

    Chatboks.handle_integration_command(app, f"/integration approve {request_id}", source="terminal")
    Chatboks.handle_integration_command(app, f"/integration dispatch {request_id}", source="terminal")

    queued = app.integration_request_queue().get(request_id)
    assert queued is not None
    assert queued.status == "dispatched"
    assert queued.execution_session_id == "session-command-001"
    execution = app.integration_execution_registry().get_for_request(request_id)
    assert execution is not None
    assert execution.status == "waiting_for_runner"
    app.start_integration_execution.assert_called_once_with(execution.execution_id)
    app.handle_user_input.assert_not_called()
    assert execution.execution_id in app.stream.system.call_args.args[0]


def test_structured_ticket_scope_is_visible_locally_and_dispatches_without_a_legacy_prompt(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path, structured=True)

    Chatboks.handle_integration_command(app, "/integration pending", source="terminal")

    pending_output = app.stream.system.call_args.args[0]
    assert "Review the bounded ticket execution." in pending_output
    assert "constraints=1" in pending_output
    assert "verify=1" in pending_output
    assert "budget=4 steps/120s" in pending_output
    assert "risk=high" in pending_output
    assert "reversibility=unknown" in pending_output

    Chatboks.handle_integration_command(app, f"/integration approve {request_id}", source="terminal")
    assert "approval receipt" in app.stream.system.call_args.args[0]
    Chatboks.handle_integration_command(app, "/integration all", source="terminal")
    assert "approval_expires=" in app.stream.system.call_args.args[0]
    Chatboks.handle_integration_command(app, f"/integration dispatch {request_id}", source="terminal")

    queued = app.integration_request_queue().get(request_id)
    assert queued is not None
    assert queued.status == "dispatched"
    app.start_integration_execution.assert_called_once()


def test_local_operator_cancels_only_the_verified_isolated_runner(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)
    queue = app.integration_request_queue()
    queue.approve(request_id)
    execution = app.integration_execution_registry().reserve(request_id)
    queue.mark_dispatched(request_id, "session-command-001")
    app.integration_execution_registry().attach_runner(execution.execution_id, 4242)
    app.integration_execution_registry().start(execution.execution_id, execution.execution_id)

    Chatboks.handle_integration_command(app, f"/integration cancel {request_id}", source="terminal")

    cancelled = app.integration_execution_registry().get(execution.execution_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    app.verify_integration_execution.assert_called_once()
    app.cancel_integration_execution.assert_called_once()
    assert cancelled.execution_id in app.stream.system.call_args.args[0]


def test_local_operator_does_not_cancel_when_runner_ownership_cannot_be_proven(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)
    queue = app.integration_request_queue()
    queue.approve(request_id)
    execution = app.integration_execution_registry().reserve(request_id)
    queue.mark_dispatched(request_id, "session-command-001")
    app.integration_execution_registry().attach_runner(execution.execution_id, 4242)
    app.integration_execution_registry().start(execution.execution_id, execution.execution_id)
    app.verify_integration_execution.side_effect = IntegrationExecutionTerminationError("ownership mismatch")

    Chatboks.handle_integration_command(app, f"/integration cancel {request_id}", source="terminal")

    unchanged = app.integration_execution_registry().get(execution.execution_id)
    assert unchanged is not None
    assert unchanged.status == "running"
    app.cancel_integration_execution.assert_not_called()
    assert "not completed" in app.stream.system.call_args.args[0]


def test_local_operator_marks_an_unverified_worker_interrupted_during_recovery(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)
    queue = app.integration_request_queue()
    queue.approve(request_id)
    execution = app.integration_execution_registry().reserve(request_id)
    queue.mark_dispatched(request_id, "session-command-001")
    app.integration_execution_registry().attach_runner(execution.execution_id, 4242)
    app.integration_execution_registry().start(execution.execution_id, execution.execution_id)

    Chatboks.handle_integration_command(app, f"/integration recover {request_id}", source="terminal")

    recovered = app.integration_execution_registry().get(execution.execution_id)
    assert recovered is not None
    assert recovered.status == "interrupted"
    app.integration_execution_is_owned.assert_called_once()
    assert "marked interrupted" in app.stream.system.call_args.args[0]


def test_local_recovery_marks_an_unverified_agent_step_uncertain(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)
    queue = app.integration_request_queue()
    queue.approve(request_id)
    execution = app.integration_execution_registry().reserve(request_id)
    queue.mark_dispatched(request_id, "session-command-001")
    app.integration_execution_registry().attach_runner(execution.execution_id, 4242)
    app.integration_execution_registry().start(execution.execution_id, execution.execution_id)
    checkpoints = IntegrationCheckpointRegistry(default_checkpoint_registry_path(tmp_path))
    checkpoints.prepare(execution.execution_id, request_id)
    checkpoints.begin_agent_step(execution.execution_id)

    Chatboks.handle_integration_command(app, f"/integration recover {request_id}", source="terminal")

    checkpoint = checkpoints.get(execution.execution_id)
    assert checkpoint is not None
    assert checkpoint.state == "uncertain"
    assert checkpoint.recovery_reason == "worker_not_verified_during_recovery"
    Chatboks.handle_integration_command(app, "/integration all", source="terminal")
    assert "checkpoint=uncertain" in app.stream.system.call_args.args[0]
    assert "checkpoint_reason=worker_not_verified_during_recovery" in app.stream.system.call_args.args[0]


def test_local_recovery_allows_explicit_safe_resume_before_agent_step(tmp_path: Path):
    app = _app(tmp_path)
    request_id = _queue_request(tmp_path)
    queue = app.integration_request_queue()
    queue.approve(request_id)
    execution = app.integration_execution_registry().reserve(request_id)
    queue.mark_dispatched(request_id, "session-command-001")
    app.integration_execution_registry().attach_runner(execution.execution_id, 4242)
    app.integration_execution_registry().start(execution.execution_id, execution.execution_id)
    checkpoints = IntegrationCheckpointRegistry(default_checkpoint_registry_path(tmp_path))
    checkpoints.prepare(execution.execution_id, request_id)

    Chatboks.handle_integration_command(app, f"/integration recover {request_id}", source="terminal")
    Chatboks.handle_integration_command(app, f"/integration resume {request_id}", source="terminal")

    retried = app.integration_execution_registry().get(execution.execution_id)
    assert retried is not None
    assert retried.status == "waiting_for_runner"
    assert checkpoints.get(execution.execution_id).state == "prepared"
    app.start_integration_execution.assert_called_once_with(execution.execution_id)
    assert "resumed before its agent step" in app.stream.system.call_args.args[0]


def test_local_recovery_leaves_a_verified_worker_running(tmp_path: Path):
    app = _app(tmp_path)
    app.integration_execution_is_owned.return_value = True
    request_id = _queue_request(tmp_path)
    queue = app.integration_request_queue()
    queue.approve(request_id)
    execution = app.integration_execution_registry().reserve(request_id)
    queue.mark_dispatched(request_id, "session-command-001")
    app.integration_execution_registry().attach_runner(execution.execution_id, 4242)
    app.integration_execution_registry().start(execution.execution_id, execution.execution_id)

    Chatboks.handle_integration_command(app, f"/integration recover {request_id}", source="terminal")

    unchanged = app.integration_execution_registry().get(execution.execution_id)
    assert unchanged is not None
    assert unchanged.status == "running"
    assert "no recovery action" in app.stream.system.call_args.args[0]
