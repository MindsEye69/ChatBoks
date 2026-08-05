"""Tests for passive trajectory-health diagnostics."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator import Chatboks


def _make_app(root: Path) -> Chatboks:
    app = Chatboks.__new__(Chatboks)
    app.project = "test"
    app.trigger = "manual"
    app.config = {"trajectory_health": {"watch_after": 3}}
    app.proj_config = {"agents": ["codex"]}
    app.proj_path = root
    app.chatboks_md = root / "chatboks.md"
    app.state_file = root / ".chatboks" / "state.json"
    app.stream = MagicMock()
    app.state = Chatboks.normalize_state(
        app,
        {
            "session": "test",
            "round": 1,
            "status": "active",
            "active_task": "Implement the bounded test task.",
            "context": {"token_counts": {}},
        },
    )
    app.save_state = MagicMock()
    return app


def test_health_command_is_local_before_any_agent_call() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.run_agent_round = MagicMock()

        app.handle_user_input("/health")

        output = app.stream.system.call_args.args[0]
        assert "Trajectory health: passive diagnostics only" in output
        assert "no agent-call observations yet" in output
        app.run_agent_round.assert_not_called()


def test_trajectory_health_warns_on_repeated_agent_calls() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.start_trajectory_health("Implement the bounded test task.")

        for _ in range(3):
            app.record_trajectory_attempt("codex", "respond", 1.0, "completed", "short reply")

        lines = app.trajectory_health_lines()

        assert "Status: WATCH" in "\n".join(lines)
        assert "3 repeated codex/respond calls" in "\n".join(lines)
        assert "3 consecutive" in "\n".join(lines)


def test_trajectory_health_warns_when_execution_worktree_does_not_change() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.start_trajectory_health("Implement the bounded test task.")
        app.capture_worktree_progress_digest = MagicMock(return_value="0123456789abcdef")

        for _ in range(3):
            app.record_trajectory_attempt("codex", "execute", 5.0, "completed", "done")

        output = "\n".join(app.trajectory_health_lines())
        assert "Status: WATCH" in output
        assert "no worktree change across 3 execution calls" in output
        assert "unchanged across 3 observed execution call(s)" in output


def test_trajectory_health_sanitizes_untrusted_state_records() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))

        health = app.normalized_trajectory_health(
            {
                "task_fingerprint": "not-a-digest",
                "turns": [
                    {
                        "agent": "codex" * 100,
                        "mode": "execute",
                        "outcome": "completed",
                        "duration_seconds": -1,
                        "estimated_output_tokens": -3,
                        "worktree_digest": "not-a-digest",
                    }
                ],
            }
        )

        assert health["task_fingerprint"] == "none"
        assert health["turns"][0]["duration_seconds"] == 0.0
        assert health["turns"][0]["estimated_output_tokens"] == 0
        assert health["turns"][0]["worktree_digest"] is None


def test_agent_call_records_passive_trajectory_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app(Path(tmp))
        app.config = {
            "agents": {"codex": {"token_warning": 100_000}},
            "context": {"max_token_recovery_retries": 0, "max_timeout_recovery_retries": 0},
        }
        app.state["context"]["token_counts"]["codex"] = 0
        app.context = MagicMock()
        app.context.build.return_value = "context"
        agent = MagicMock()
        agent.call.return_value = "completed output\n>>> TASK_COMPLETE"
        app.router = MagicMock()
        app.router.get_agent.return_value = agent

        response = app.call_agent_with_token_recovery("codex", mode="respond")

        assert response == "completed output\n>>> TASK_COMPLETE"
        turn = app.state["trajectory_health"]["turns"][-1]
        assert turn["agent"] == "codex"
        assert turn["mode"] == "respond"
        assert turn["outcome"] == "completed"
        assert turn["estimated_output_tokens"] > 0
