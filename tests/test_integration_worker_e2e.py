"""End-to-end coverage for an approved request's isolated worker lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time
from unittest.mock import MagicMock

from integration_executions import IntegrationExecutionRegistry, default_execution_registry_path
from integration_proofs import PairedProofDecision
from orchestrator import Chatboks
from remote_control import RemoteSession


def _write_worker_config(config_path: Path, project_path: Path) -> None:
    config_path.write_text(
        json.dumps(
            {
                "context": {"codegraph": {"enabled": False}},
                "agents": {
                    "antigravity": {
                        "cli": sys.executable,
                        "dynamic_timeouts": False,
                        "first_output_timeout": 5,
                    }
                },
                "projects": {
                    "worker-e2e": {
                        "path": str(project_path),
                        "agents": ["antigravity"],
                        "primary": "antigravity",
                        "codegraph": False,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _queue_verified_request(app: Chatboks) -> str:
    request = app.integration_request_queue().submit_verified(
        PairedProofDecision(
            request={
                "requestId": "request-worker-e2e-001",
                "contractVersion": "0.1.0",
                "ticketId": "CBX-001",
                "targetApplicationId": "chatboks",
                "capabilityId": "execution.lifecycle",
                "correlationId": "correlation-worker-e2e-001",
                "requestedAt": "2026-08-05T09:00:00Z",
                "input": {"prompt": "Complete the harmless worker lifecycle test."},
            },
            client_id="dasdashboard",
            key_id="dash-client-key",
            proof_id="proof-worker-e2e-001",
            idempotent=False,
        )
    )
    return request.request_id


def test_approved_request_runs_in_worker_and_is_observable_without_ui_automation(tmp_path: Path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "run").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "prompt = sys.stdin.read()\n"
        "Path('received-worker-prompt.txt').write_text(prompt, encoding='utf-8')\n"
        "print('Harmless test agent completed the request.')\n"
        "print('>>> TASK_COMPLETE')\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    _write_worker_config(config_path, project_path)
    app = Chatboks("worker-e2e", config_path=config_path)
    app.ensure_project_files()
    app.stream = MagicMock()
    request_id = _queue_verified_request(app)

    Chatboks.handle_integration_command(app, f"/integration approve {request_id}", source="terminal")
    Chatboks.handle_integration_command(app, f"/integration dispatch {request_id}", source="terminal")

    registry = IntegrationExecutionRegistry(default_execution_registry_path(project_path))
    deadline = time.monotonic() + 10
    execution = registry.get_for_request(request_id)
    while execution is not None and execution.status in {"waiting_for_runner", "running"}:
        if time.monotonic() >= deadline:
            raise AssertionError("Isolated integration worker did not finish within ten seconds.")
        time.sleep(0.05)
        execution = registry.get_for_request(request_id)

    assert execution is not None
    assert execution.status == "succeeded"
    result_path = (
        project_path / ".chatboks" / "integration-executions" / execution.execution_id / "result.md"
    )
    assert result_path.read_text(encoding="utf-8").endswith(">>> TASK_COMPLETE")
    received_prompt = (project_path / "received-worker-prompt.txt").read_text(encoding="utf-8")
    assert "[VERIFIED INTEGRATION EXECUTION]" in received_prompt
    assert "Complete the harmless worker lifecycle test." in received_prompt

    remote_session = RemoteSession.__new__(RemoteSession)
    remote_session.app = SimpleNamespace(proj_path=project_path)
    event_payload = remote_session.integration_execution_events(request_id)

    assert event_payload is not None
    assert event_payload["execution"]["id"] == execution.execution_id
    assert event_payload["execution"]["status"] == "succeeded"
    event_types = [event["type"] for event in event_payload["events"]]
    assert "execution_reserved" in event_types
    assert "execution_started" in event_types
    assert "execution_succeeded" in event_types
    assert "input" not in event_payload
    assert "result" not in event_payload
